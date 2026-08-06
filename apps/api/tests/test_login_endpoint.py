from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.jwt import decode_access_token
from db import get_session
from main import app
from models.session import Session
from models.user import User

client = TestClient(app)

TEST_EMAIL = "login-test-1@example.com"
TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email.like("login-test-%")))
        users = result.scalars().all()
        for user in users:
            session_result = await session.execute(
                select(Session).where(Session.user_id == user.id)
            )
            for s in session_result.scalars().all():
                await session.delete(s)
            await session.delete(user)
        await session.commit()


async def _signup(email: str = TEST_EMAIL, password: str = TEST_PASSWORD) -> None:
    client.post(
        "/auth/signup", json={"email": email, "password": password, "full_name": "Login Test"}
    )


@pytest.mark.anyio
async def test_login_with_correct_credentials_returns_tokens() -> None:
    await _signup()
    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    user_id = decode_access_token(body["access_token"])
    async with get_session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.email == TEST_EMAIL


@pytest.mark.anyio
async def test_login_creates_a_session_row() -> None:
    await _signup()
    client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == TEST_EMAIL))
        user = result.scalar_one()
        session_result = await session.execute(select(Session).where(Session.user_id == user.id))
        sessions = session_result.scalars().all()
        assert len(sessions) == 1
        assert sessions[0].revoked_at is None


@pytest.mark.anyio
async def test_login_wrong_password_returns_401() -> None:
    await _signup()
    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": "wrong password"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.anyio
async def test_login_nonexistent_user_returns_same_401_as_wrong_password() -> None:
    response = client.post(
        "/auth/login", json={"email": "login-test-nosuchuser@example.com", "password": "whatever"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."


@pytest.mark.anyio
async def test_access_token_contains_correct_user_id() -> None:
    await _signup()
    response = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    access_token = response.json()["access_token"]

    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == TEST_EMAIL))
        user = result.scalar_one()

    assert decode_access_token(access_token) == user.id
