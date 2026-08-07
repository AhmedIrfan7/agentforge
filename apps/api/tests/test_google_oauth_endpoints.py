"""Integration tests against the real FastAPI app for routers/oauth.py
(roadmap step 076).

Google's own endpoints obviously can't be hit in CI — auth.oauth.
exchange_google_code_for_userinfo is monkeypatched at the point routers/
oauth.py imported it (patching auth.oauth's own module attribute would
NOT affect the name already bound into routers/oauth's namespace). The
CSRF state-cookie mechanics and the account-linking/creation logic
around that boundary are exercised for real, through the actual HTTP
endpoints — only the third-party network call itself is faked.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.oauth import GoogleUserInfo
from auth.passwords import hash_password
from db import get_session
from main import app
from models.oauth_identity import OAuthIdentity
from models.session import Session
from models.user import User
from tests.helpers import signup_and_login

client = TestClient(app)


async def _cleanup_user(email: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            return
        session_result = await session.execute(select(Session).where(Session.user_id == user.id))
        for s in session_result.scalars().all():
            await session.delete(s)
        identity_result = await session.execute(
            select(OAuthIdentity).where(OAuthIdentity.user_id == user.id)
        )
        for identity in identity_result.scalars().all():
            await session.delete(identity)
        await session.delete(user)
        await session.commit()


def _get_login_state() -> str:
    """Follows this test suite's real /auth/google/login endpoint to get
    a genuine state value + cookie pair (set on `client`'s cookie jar),
    exactly as a browser would before Google ever gets involved."""
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    state: str = parse_qs(urlparse(location).query)["state"][0]
    return state


def test_google_login_redirects_to_google_with_state_cookie() -> None:
    client.cookies.clear()
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    query = parse_qs(urlparse(location).query)
    assert "state" in query
    assert query["response_type"] == ["code"]
    assert "oauth_state" in response.cookies


def test_google_callback_without_state_cookie_returns_401() -> None:
    client.cookies.clear()
    response = client.get("/auth/google/callback", params={"code": "irrelevant", "state": "x"})
    assert response.status_code == 401


def test_google_callback_with_mismatched_state_returns_401() -> None:
    _get_login_state()
    response = client.get(
        "/auth/google/callback", params={"code": "irrelevant", "state": "not-the-real-state"}
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_google_callback_rejects_unverified_email(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_exchange(code: str) -> GoogleUserInfo:
        return GoogleUserInfo(
            subject="google-unverified-1",
            email="endpoint-test-oauth-unverified@example.com",
            email_verified=False,
            full_name="Unverified",
        )

    monkeypatch.setattr("routers.oauth.exchange_google_code_for_userinfo", fake_exchange)

    state = _get_login_state()
    response = client.get("/auth/google/callback", params={"code": "fake-code", "state": state})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_google_callback_creates_new_user(monkeypatch: pytest.MonkeyPatch) -> None:
    email = "endpoint-test-oauth-newuser@example.com"

    async def fake_exchange(code: str) -> GoogleUserInfo:
        return GoogleUserInfo(
            subject="google-subject-newuser-1",
            email=email,
            email_verified=True,
            full_name="New Googler",
        )

    monkeypatch.setattr("routers.oauth.exchange_google_code_for_userinfo", fake_exchange)

    try:
        state = _get_login_state()
        response = client.get("/auth/google/callback", params={"code": "fake-code", "state": state})
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body

        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one()
            assert user.is_email_verified is True
            assert user.hashed_password is None
            assert user.full_name == "New Googler"

            identity_result = await session.execute(
                select(OAuthIdentity).where(OAuthIdentity.user_id == user.id)
            )
            identity = identity_result.scalar_one()
            assert identity.provider == "google"
            assert identity.provider_user_id == "google-subject-newuser-1"
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_google_callback_links_existing_password_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = "endpoint-test-oauth-linkexisting@example.com"

    async def fake_exchange(code: str) -> GoogleUserInfo:
        return GoogleUserInfo(
            subject="google-subject-linkexisting-1",
            email=email,
            email_verified=True,
            full_name="Existing User",
        )

    monkeypatch.setattr("routers.oauth.exchange_google_code_for_userinfo", fake_exchange)

    try:
        # A password-based account that never verified its email.
        async with get_session() as session:
            session.add(
                User(
                    email=email,
                    full_name="Existing User",
                    hashed_password=hash_password("correct horse battery staple"),
                    is_email_verified=False,
                )
            )
            await session.commit()

        state = _get_login_state()
        response = client.get("/auth/google/callback", params={"code": "fake-code", "state": state})
        assert response.status_code == 200

        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            users = result.scalars().all()
            # Linked, not duplicated.
            assert len(users) == 1
            user = users[0]
            # Google's verification satisfies ours too.
            assert user.is_email_verified is True
            # The password login path must still work — linking a Google
            # identity doesn't wipe out the existing credential.
            assert user.hashed_password is not None
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_google_callback_reuses_existing_identity_on_repeat_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = "endpoint-test-oauth-repeat@example.com"

    async def fake_exchange(code: str) -> GoogleUserInfo:
        return GoogleUserInfo(
            subject="google-subject-repeat-1", email=email, email_verified=True, full_name="Repeat"
        )

    monkeypatch.setattr("routers.oauth.exchange_google_code_for_userinfo", fake_exchange)

    try:
        first_state = _get_login_state()
        first = client.get(
            "/auth/google/callback", params={"code": "fake-code-1", "state": first_state}
        )
        assert first.status_code == 200

        second_state = _get_login_state()
        second = client.get(
            "/auth/google/callback", params={"code": "fake-code-2", "state": second_state}
        )
        assert second.status_code == 200

        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.email == email))
            users = user_result.scalars().all()
            assert len(users) == 1

            identity_result = await session.execute(
                select(OAuthIdentity).where(OAuthIdentity.user_id == users[0].id)
            )
            identities = identity_result.scalars().all()
            assert len(identities) == 1
    finally:
        await _cleanup_user(email)


def test_google_callback_google_exchange_failure_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from errors import UnauthorizedError

    async def failing_exchange(code: str) -> GoogleUserInfo:
        raise UnauthorizedError("Google sign-in failed.")

    monkeypatch.setattr("routers.oauth.exchange_google_code_for_userinfo", failing_exchange)

    state = _get_login_state()
    response = client.get("/auth/google/callback", params={"code": "bad-code", "state": state})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_signup_and_login_still_works_after_oauth_router_registered() -> None:
    """Not really an OAuth test — a cheap sanity check that adding a
    second router under /auth/* (oauth.router's prefix is /auth/google,
    nested under auth.router's /auth) didn't shadow or break the existing
    password-based routes."""
    email = "endpoint-test-oauth-sanity@example.com"
    try:
        token = signup_and_login(
            client, email=email, password="correct horse battery staple", full_name="Sanity"
        )
        assert token
    finally:
        await _cleanup_user(email)
