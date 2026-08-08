"""End-to-end auth lifecycle test (roadmap step 080):
signup -> verify -> login -> refresh -> logout, as one continuous chain
using real data threaded through each step -- not fresh, isolated
fixtures per assertion the way the individual endpoint test files
(test_signup_endpoint.py, test_verify_email_endpoint.py, etc.) do. The
value here is different: it proves the whole realistic user journey
works together (the verification token created during signup actually
verifies the same account that then logs in; the access token from that
login actually works against a protected route; the refresh token from
that same login actually rotates and then actually dies on logout), the
kind of integration gap that per-endpoint tests using throwaway data
can't catch even if each one passes individually.

Signup's own internally-generated verification token isn't retrievable
in a test (only its hash is stored, and notifications/email.py's stub
only logs the raw one) -- same reasoning as
test_verify_email_endpoint.py, a second, independent token is created
via the real repository/generate_verification_token() to exercise the
actual verify-email code path against the same account signup created.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.verification import generate_verification_token
from db import get_session
from main import app
from models.session import Session
from models.user import User
from repositories.verification_token import VerificationTokenRepository
from tests.helpers import auth_headers

client = TestClient(app)

EMAIL = "endpoint-test-fullflow@example.com"
PASSWORD = "correct horse battery staple"


async def _cleanup() -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == EMAIL))
        user = result.scalar_one_or_none()
        if user is None:
            return
        session_result = await session.execute(select(Session).where(Session.user_id == user.id))
        for s in session_result.scalars().all():
            await session.delete(s)
        await session.delete(user)
        await session.commit()


@pytest.mark.anyio
async def test_full_auth_flow_signup_verify_login_refresh_logout() -> None:
    try:
        # 1. Signup — creates an unverified user.
        signup_response = client.post(
            "/auth/signup",
            json={"email": EMAIL, "password": PASSWORD, "full_name": "Full Flow"},
        )
        assert signup_response.status_code == 201
        user_id = signup_response.json()["id"]

        async with get_session() as session:
            user = await session.get(User, user_id)
            assert user is not None
            assert user.is_email_verified is False

        # 2. Verify — the same account signup just created.
        raw_token, token_hash, expires_at = generate_verification_token()
        async with get_session() as session:
            await VerificationTokenRepository(session).create(
                user_id=user_id,
                token_hash=token_hash,
                purpose="email_verify",
                expires_at=expires_at,
            )
            await session.commit()

        verify_response = client.post("/auth/verify-email", json={"token": raw_token})
        assert verify_response.status_code == 204

        async with get_session() as session:
            user = await session.get(User, user_id)
            assert user is not None
            assert user.is_email_verified is True

        # 3. Login — with the exact credentials signup created.
        login_response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert login_response.status_code == 200
        login_body = login_response.json()
        first_access_token = login_body["access_token"]
        first_refresh_token = login_body["refresh_token"]

        # The access token from login actually works against a real
        # protected route, not just "looks like a JWT".
        list_orgs = client.get("/organizations", headers=auth_headers(first_access_token))
        assert list_orgs.status_code == 200

        # 4. Refresh — with the refresh token from that same login.
        refresh_response = client.post("/auth/refresh", json={"refresh_token": first_refresh_token})
        assert refresh_response.status_code == 200
        refresh_body = refresh_response.json()
        second_access_token = refresh_body["access_token"]
        second_refresh_token = refresh_body["refresh_token"]
        assert second_access_token != first_access_token
        assert second_refresh_token != first_refresh_token

        # Single-use rotation: the original refresh token from login is
        # now dead, even though it was never explicitly logged out.
        reuse_original = client.post("/auth/refresh", json={"refresh_token": first_refresh_token})
        assert reuse_original.status_code == 401

        # The new access token from refresh works too.
        list_orgs_again = client.get("/organizations", headers=auth_headers(second_access_token))
        assert list_orgs_again.status_code == 200

        # 5. Logout — with the current (rotated) refresh token.
        logout_response = client.post("/auth/logout", json={"refresh_token": second_refresh_token})
        assert logout_response.status_code == 204

        # The refresh token that was just logged out can no longer be
        # redeemed for new tokens.
        refresh_after_logout = client.post(
            "/auth/refresh", json={"refresh_token": second_refresh_token}
        )
        assert refresh_after_logout.status_code == 401

        # By design, logout revokes the refresh token (models/session.py),
        # not the already-issued access token — a stateless JWT (auth/jwt.py)
        # has no server-side record to revoke, so it keeps working until
        # its own short natural expiry. Not asserted as a failure here;
        # that would be testing for a bug that doesn't exist.
    finally:
        await _cleanup()
