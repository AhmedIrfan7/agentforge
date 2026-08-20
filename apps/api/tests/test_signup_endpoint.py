from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.passwords import verify_password
from db import get_session
from main import app
from models.user import User

client = TestClient(app)


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email.like("signup-test-%@example.com"))
        )
        for user in result.scalars().all():
            await session.delete(user)
        await session.commit()


@pytest.mark.anyio
async def test_signup_creates_user_with_hashed_password() -> None:
    response = client.post(
        "/auth/signup",
        json={
            "email": "signup-test-1@example.com",
            "password": "correct horse battery staple",
            "full_name": "Test Signup",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "signup-test-1@example.com"
    assert body["is_platform_admin"] is False
    assert "password" not in body
    assert "hashed_password" not in body

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email == "signup-test-1@example.com")
        )
        user = result.scalar_one()
        assert user.hashed_password is not None
        assert user.hashed_password != "correct horse battery staple"
        assert verify_password("correct horse battery staple", user.hashed_password)


@pytest.mark.anyio
async def test_signup_duplicate_email_returns_409() -> None:
    payload = {
        "email": "signup-test-dup@example.com",
        "password": "correct horse battery staple",
        "full_name": "First",
    }
    client.post("/auth/signup", json=payload)
    response = client.post("/auth/signup", json={**payload, "full_name": "Second"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


@pytest.mark.anyio
async def test_signup_rejects_short_password() -> None:
    response = client.post(
        "/auth/signup",
        json={
            "email": "signup-test-short@example.com",
            "password": "short",
            "full_name": "Test",
        },
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_signup_rejects_invalid_email() -> None:
    response = client.post(
        "/auth/signup",
        json={
            "email": "not-an-email",
            "password": "correct horse battery staple",
            "full_name": "Test",
        },
    )
    assert response.status_code == 422
