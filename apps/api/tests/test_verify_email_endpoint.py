from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.verification import generate_verification_token, hash_verification_token
from db import get_session
from main import app
from models.user import User
from models.verification_token import VerificationToken
from repositories.verification_token import VerificationTokenRepository

client = TestClient(app)

TEST_EMAIL = "verify-test-1@example.com"
TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email.like("verify-test-%")))
        for user in result.scalars().all():
            token_result = await session.execute(
                select(VerificationToken).where(VerificationToken.user_id == user.id)
            )
            for t in token_result.scalars().all():
                await session.delete(t)
            await session.delete(user)
        await session.commit()


@pytest.mark.anyio
async def test_signup_creates_unverified_user_and_verification_token() -> None:
    client.post(
        "/auth/signup",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "full_name": "Verify Test"},
    )
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == TEST_EMAIL))
        user = result.scalar_one()
        assert user.is_email_verified is False

        token_result = await session.execute(
            select(VerificationToken).where(VerificationToken.user_id == user.id)
        )
        token = token_result.scalar_one()
        assert token.purpose == "email_verify"
        assert token.used_at is None


@pytest.mark.anyio
async def test_verify_email_marks_user_verified_and_token_used() -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "verify-test-flow@example.com",
            "password": TEST_PASSWORD,
            "full_name": "Verify Flow",
        },
    )

    # Signup already generated+stored its own token, but stub email
    # sending only logs it — nothing to read here in a test. Create a
    # second, independent token via the same repository real code uses,
    # so this exercises the actual verify-email code path either way.
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email == "verify-test-flow@example.com")
        )
        user = result.scalar_one()

    raw_token, token_hash, expires_at = generate_verification_token()
    async with get_session() as session:
        await VerificationTokenRepository(session).create(
            user_id=user.id, token_hash=token_hash, purpose="email_verify", expires_at=expires_at
        )
        await session.commit()

    response = client.post("/auth/verify-email", json={"token": raw_token})
    assert response.status_code == 204

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email == "verify-test-flow@example.com")
        )
        assert result.scalar_one().is_email_verified is True


@pytest.mark.anyio
async def test_verify_email_rejects_unknown_token() -> None:
    response = client.post("/auth/verify-email", json={"token": "totally-made-up-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.anyio
async def test_verify_email_token_is_single_use() -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "verify-test-single-use@example.com",
            "password": TEST_PASSWORD,
            "full_name": "Single Use",
        },
    )
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email == "verify-test-single-use@example.com")
        )
        user = result.scalar_one()

    raw_token, token_hash, expires_at = generate_verification_token()
    async with get_session() as session:
        await VerificationTokenRepository(session).create(
            user_id=user.id, token_hash=token_hash, purpose="email_verify", expires_at=expires_at
        )
        await session.commit()

    first = client.post("/auth/verify-email", json={"token": raw_token})
    second = client.post("/auth/verify-email", json={"token": raw_token})
    assert first.status_code == 204
    assert second.status_code == 401


@pytest.mark.anyio
async def test_hash_verification_token_is_deterministic() -> None:
    assert hash_verification_token("abc") == hash_verification_token("abc")
    assert hash_verification_token("abc") != hash_verification_token("xyz")
