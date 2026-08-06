from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.verification import generate_verification_token
from db import get_session
from main import app
from models.user import User
from models.verification_token import VerificationToken
from repositories.verification_token import VerificationTokenRepository

client = TestClient(app)

TEST_EMAIL = "magiclink-test-1@example.com"
TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email.like("magiclink-test-%")))
        for user in result.scalars().all():
            token_result = await session.execute(
                select(VerificationToken).where(VerificationToken.user_id == user.id)
            )
            for t in token_result.scalars().all():
                await session.delete(t)
            await session.delete(user)
        await session.commit()


@pytest.mark.anyio
async def test_request_for_existing_user_returns_204() -> None:
    client.post(
        "/auth/signup",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "full_name": "Magic Link Test"},
    )
    response = client.post("/auth/magic-link/request", json={"email": TEST_EMAIL})
    assert response.status_code == 204


@pytest.mark.anyio
async def test_request_for_nonexistent_user_also_returns_204() -> None:
    # Same response either way — anti-enumeration.
    response = client.post(
        "/auth/magic-link/request", json={"email": "magiclink-test-nosuchuser@example.com"}
    )
    assert response.status_code == 204


@pytest.mark.anyio
async def test_request_creates_a_magic_link_token_only_for_existing_user() -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "magiclink-test-token@example.com",
            "password": TEST_PASSWORD,
            "full_name": "Token Test",
        },
    )
    client.post("/auth/magic-link/request", json={"email": "magiclink-test-token@example.com"})

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email == "magiclink-test-token@example.com")
        )
        user = result.scalar_one()
        token_result = await session.execute(
            select(VerificationToken).where(
                VerificationToken.user_id == user.id, VerificationToken.purpose == "magic_link"
            )
        )
        assert len(token_result.scalars().all()) == 1


@pytest.mark.anyio
async def test_verify_magic_link_issues_tokens_and_is_single_use() -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "magiclink-test-verify@example.com",
            "password": TEST_PASSWORD,
            "full_name": "Verify Test",
        },
    )
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email == "magiclink-test-verify@example.com")
        )
        user = result.scalar_one()

    raw_token, token_hash, expires_at = generate_verification_token()
    async with get_session() as session:
        await VerificationTokenRepository(session).create(
            user_id=user.id, token_hash=token_hash, purpose="magic_link", expires_at=expires_at
        )
        await session.commit()

    first = client.post("/auth/magic-link/verify", json={"token": raw_token})
    assert first.status_code == 200
    body = first.json()
    assert body["access_token"]
    assert body["refresh_token"]

    second = client.post("/auth/magic-link/verify", json={"token": raw_token})
    assert second.status_code == 401


@pytest.mark.anyio
async def test_verify_magic_link_rejects_unknown_token() -> None:
    response = client.post("/auth/magic-link/verify", json={"token": "totally-made-up"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.anyio
async def test_email_verify_token_cannot_be_used_as_magic_link() -> None:
    """purpose isolation: a token minted for one flow must not work in another."""
    client.post(
        "/auth/signup",
        json={
            "email": "magiclink-test-cross-purpose@example.com",
            "password": TEST_PASSWORD,
            "full_name": "Cross Purpose",
        },
    )
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email == "magiclink-test-cross-purpose@example.com")
        )
        user = result.scalar_one()

    raw_token, token_hash, expires_at = generate_verification_token()
    async with get_session() as session:
        await VerificationTokenRepository(session).create(
            user_id=user.id, token_hash=token_hash, purpose="email_verify", expires_at=expires_at
        )
        await session.commit()

    response = client.post("/auth/magic-link/verify", json={"token": raw_token})
    assert response.status_code == 401
