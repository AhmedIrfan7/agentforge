from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session
from main import app
from models.session import Session
from models.user import User

client = TestClient(app)

TEST_EMAIL = "logout-test-1@example.com"
TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email.like("logout-test-%")))
        for user in result.scalars().all():
            session_result = await session.execute(
                select(Session).where(Session.user_id == user.id)
            )
            for s in session_result.scalars().all():
                await session.delete(s)
            await session.delete(user)
        await session.commit()


@pytest.mark.anyio
async def test_logout_revokes_the_session() -> None:
    client.post(
        "/auth/signup",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "full_name": "Logout Test"},
    )
    login_response = client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_response.status_code == 204

    # The revoked refresh token must no longer work for refresh.
    refresh_response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 401


@pytest.mark.anyio
async def test_logout_with_unknown_token_is_still_204() -> None:
    response = client.post("/auth/logout", json={"refresh_token": "never-existed"})
    assert response.status_code == 204


@pytest.mark.anyio
async def test_logout_twice_with_same_token_is_still_204() -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "logout-test-double@example.com",
            "password": TEST_PASSWORD,
            "full_name": "Double Logout",
        },
    )
    login_response = client.post(
        "/auth/login",
        json={"email": "logout-test-double@example.com", "password": TEST_PASSWORD},
    )
    refresh_token = login_response.json()["refresh_token"]

    first = client.post("/auth/logout", json={"refresh_token": refresh_token})
    second = client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert first.status_code == 204
    assert second.status_code == 204
