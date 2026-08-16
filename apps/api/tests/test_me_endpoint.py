"""Tests for GET /auth/me (roadmap step 233) -- added as the real
backend complement the dashboard shell needs: `TokenResponse` (login's
own response) carries only tokens, no user identity, so a client has no
honest way to show "who's logged in" without this. Uses the same
`get_current_user_id` dependency every other authenticated route in
this codebase already shares -- no new auth mechanism, just a new real
caller of it."""

from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session
from main import app
from models.session import Session
from models.user import User

client = TestClient(app)

TEST_EMAIL = "me-endpoint-test-1@example.com"
TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email.like("me-endpoint-test-%")))
        users = result.scalars().all()
        for user in users:
            session_result = await session.execute(
                select(Session).where(Session.user_id == user.id)
            )
            for s in session_result.scalars().all():
                await session.delete(s)
            await session.delete(user)
        await session.commit()


def _signup_and_login(email: str = TEST_EMAIL, password: str = TEST_PASSWORD) -> str:
    client.post("/auth/signup", json={"email": email, "password": password, "full_name": "Me Test"})
    response = client.post("/auth/login", json={"email": email, "password": password})
    access_token: str = response.json()["access_token"]
    return access_token


@pytest.mark.anyio
async def test_me_with_a_valid_token_returns_the_authenticated_user() -> None:
    access_token = _signup_and_login()
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == TEST_EMAIL
    assert body["full_name"] == "Me Test"
    assert "id" in body
    assert "created_at" in body
    assert "hashed_password" not in body


@pytest.mark.anyio
async def test_me_without_a_token_returns_401() -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_me_with_an_invalid_token_returns_401() -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401
