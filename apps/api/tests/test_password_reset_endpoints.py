from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.passwords import verify_password
from auth.verification import generate_verification_token
from db import get_session
from main import app
from models.session import Session
from models.user import User
from models.verification_token import VerificationToken
from repositories.verification_token import VerificationTokenRepository

client = TestClient(app)

TEST_PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a brand new password entirely"


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email.like("pwreset-test-%")))
        for user in result.scalars().all():
            token_result = await session.execute(
                select(VerificationToken).where(VerificationToken.user_id == user.id)
            )
            for t in token_result.scalars().all():
                await session.delete(t)
            session_result = await session.execute(
                select(Session).where(Session.user_id == user.id)
            )
            for s in session_result.scalars().all():
                await session.delete(s)
            await session.delete(user)
        await session.commit()


@pytest.mark.anyio
async def test_request_for_existing_and_nonexistent_user_both_return_204() -> None:
    client.post(
        "/auth/signup",
        json={
            "email": "pwreset-test-1@example.com",
            "password": TEST_PASSWORD,
            "full_name": "Reset Test",
        },
    )
    existing = client.post(
        "/auth/password-reset/request", json={"email": "pwreset-test-1@example.com"}
    )
    nonexistent = client.post(
        "/auth/password-reset/request", json={"email": "pwreset-test-nosuchuser@example.com"}
    )
    assert existing.status_code == 204
    assert nonexistent.status_code == 204


@pytest.mark.anyio
async def test_confirm_changes_password_and_revokes_existing_sessions() -> None:
    email = "pwreset-test-confirm@example.com"
    client.post(
        "/auth/signup", json={"email": email, "password": TEST_PASSWORD, "full_name": "Confirm"}
    )
    login_response = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    old_refresh_token = login_response.json()["refresh_token"]

    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()

    raw_token, token_hash, expires_at = generate_verification_token()
    async with get_session() as session:
        await VerificationTokenRepository(session).create(
            user_id=user.id, token_hash=token_hash, purpose="password_reset", expires_at=expires_at
        )
        await session.commit()

    confirm_response = client.post(
        "/auth/password-reset/confirm", json={"token": raw_token, "new_password": NEW_PASSWORD}
    )
    assert confirm_response.status_code == 204

    # Password actually changed.
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        refreshed = result.scalar_one()
        assert refreshed.hashed_password is not None
        assert verify_password(NEW_PASSWORD, refreshed.hashed_password)
        assert not verify_password(TEST_PASSWORD, refreshed.hashed_password)

    # Old login no longer works.
    old_login = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert old_login.status_code == 401

    # New password works.
    new_login = client.post("/auth/login", json={"email": email, "password": NEW_PASSWORD})
    assert new_login.status_code == 200

    # The session from BEFORE the reset is revoked — its refresh token no
    # longer works. This is the actual security property, not just "the
    # password changed."
    old_refresh_response = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert old_refresh_response.status_code == 401


@pytest.mark.anyio
async def test_confirm_rejects_unknown_token() -> None:
    response = client.post(
        "/auth/password-reset/confirm",
        json={"token": "totally-made-up", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_confirm_token_is_single_use() -> None:
    email = "pwreset-test-single-use@example.com"
    client.post(
        "/auth/signup",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Single Use"},
    )
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()

    raw_token, token_hash, expires_at = generate_verification_token()
    async with get_session() as session:
        await VerificationTokenRepository(session).create(
            user_id=user.id, token_hash=token_hash, purpose="password_reset", expires_at=expires_at
        )
        await session.commit()

    first = client.post(
        "/auth/password-reset/confirm", json={"token": raw_token, "new_password": NEW_PASSWORD}
    )
    second = client.post(
        "/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "yet another password"},
    )
    assert first.status_code == 204
    assert second.status_code == 401


@pytest.mark.anyio
async def test_confirm_rejects_short_new_password() -> None:
    response = client.post(
        "/auth/password-reset/confirm", json={"token": "irrelevant-here", "new_password": "short"}
    )
    assert response.status_code == 422
