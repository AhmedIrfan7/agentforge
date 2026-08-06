from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session
from main import app
from models.session import Session
from models.user import User

client = TestClient(app)

TEST_EMAIL = "refresh-test-1@example.com"
TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email.like("refresh-test-%")))
        for user in result.scalars().all():
            session_result = await session.execute(
                select(Session).where(Session.user_id == user.id)
            )
            for s in session_result.scalars().all():
                await session.delete(s)
            await session.delete(user)
        await session.commit()


async def _signup_and_login(email: str = TEST_EMAIL) -> dict[str, str]:
    client.post(
        "/auth/signup",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Refresh Test"},
    )
    response = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    result: dict[str, str] = response.json()
    return result


@pytest.mark.anyio
async def test_refresh_returns_new_tokens() -> None:
    tokens = await _signup_and_login()
    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


@pytest.mark.anyio
async def test_old_refresh_token_is_revoked_after_use() -> None:
    tokens = await _signup_and_login()
    client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    # Presenting the same (now-rotated-away) refresh token again must fail —
    # this is the actual replay-protection property, not just "a new token differs".
    replay_response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay_response.status_code == 401


@pytest.mark.anyio
async def test_refresh_with_garbage_token_returns_401() -> None:
    response = client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.anyio
async def test_refresh_with_expired_session_returns_401() -> None:
    tokens = await _signup_and_login(email="refresh-test-expired@example.com")

    async with get_session() as session:
        result = await session.execute(select(User).where(User.email.like("refresh-test-%")))
        users = result.scalars().all()
        for user in users:
            if user.email == "refresh-test-expired@example.com":
                session_result = await session.execute(
                    select(Session).where(Session.user_id == user.id)
                )
                db_session = session_result.scalar_one()
                db_session.expires_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401
