"""Integration tests against the real FastAPI app for routers/oauth.py
(roadmap step 076 Google login, step 077 generic provider abstraction).

A real third-party provider's endpoints obviously can't be hit in CI —
FakeOAuthProvider below is a genuine implementation of auth.oauth's
OAuthProvider Protocol, swapped into the PROVIDERS registry for the
duration of each test via monkeypatch.setitem. Swapping the whole
registry entry (rather than patching one function, as step 076's version
of this file did) is what the interface buys: the CSRF state-cookie
mechanics, provider lookup/404, and account-linking/creation logic are
all exercised for real, through the actual HTTP endpoints, for BOTH the
real "google" entry and a second, invented "github" entry that proves
the router genuinely doesn't hardcode Google anywhere anymore.
"""

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.oauth import PROVIDERS, OAuthUserInfo
from auth.passwords import hash_password
from db import get_session
from errors import UnauthorizedError
from main import app
from models.oauth_identity import OAuthIdentity
from models.session import Session
from models.user import User
from tests.helpers import signup_and_login

client = TestClient(app)


@dataclass
class FakeOAuthProvider:
    """A real implementation of OAuthProvider — not a mock of one — so
    these tests exercise the actual interface contract routers/oauth.py
    depends on, the same way a real second provider eventually will."""

    name: str
    result: OAuthUserInfo | Exception

    def authorize_url(self, state: str) -> str:
        return f"https://fake-provider.example/authorize?state={state}"

    async def exchange_code_for_userinfo(self, code: str) -> OAuthUserInfo:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


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


def _get_login_state(provider: str = "google") -> str:
    """Follows this test suite's real /auth/{provider}/login endpoint to
    get a genuine state value + cookie pair (set on `client`'s cookie
    jar), exactly as a browser would before the provider ever gets
    involved."""
    response = client.get(f"/auth/{provider}/login", follow_redirects=False)
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


def test_unknown_provider_login_returns_404() -> None:
    response = client.get("/auth/not-a-real-provider/login", follow_redirects=False)
    assert response.status_code == 404


def test_unknown_provider_callback_returns_404() -> None:
    response = client.get("/auth/not-a-real-provider/callback", params={"code": "x", "state": "y"})
    assert response.status_code == 404


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
    state = _get_login_state()
    monkeypatch.setitem(
        PROVIDERS,
        "google",
        FakeOAuthProvider(
            name="google",
            result=OAuthUserInfo(
                subject="google-unverified-1",
                email="endpoint-test-oauth-unverified@example.com",
                email_verified=False,
                full_name="Unverified",
            ),
        ),
    )

    response = client.get("/auth/google/callback", params={"code": "fake-code", "state": state})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_google_callback_creates_new_user(monkeypatch: pytest.MonkeyPatch) -> None:
    email = "endpoint-test-oauth-newuser@example.com"
    state = _get_login_state()
    monkeypatch.setitem(
        PROVIDERS,
        "google",
        FakeOAuthProvider(
            name="google",
            result=OAuthUserInfo(
                subject="google-subject-newuser-1",
                email=email,
                email_verified=True,
                full_name="New Googler",
            ),
        ),
    )

    try:
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
    state = _get_login_state()
    monkeypatch.setitem(
        PROVIDERS,
        "google",
        FakeOAuthProvider(
            name="google",
            result=OAuthUserInfo(
                subject="google-subject-linkexisting-1",
                email=email,
                email_verified=True,
                full_name="Existing User",
            ),
        ),
    )

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

        response = client.get("/auth/google/callback", params={"code": "fake-code", "state": state})
        assert response.status_code == 200

        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            users = result.scalars().all()
            # Linked, not duplicated.
            assert len(users) == 1
            user = users[0]
            # The provider's verification satisfies ours too.
            assert user.is_email_verified is True
            # The password login path must still work — linking an OAuth
            # identity doesn't wipe out the existing credential.
            assert user.hashed_password is not None
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_google_callback_reuses_existing_identity_on_repeat_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = "endpoint-test-oauth-repeat@example.com"
    fake_provider = FakeOAuthProvider(
        name="google",
        result=OAuthUserInfo(
            subject="google-subject-repeat-1", email=email, email_verified=True, full_name="Repeat"
        ),
    )

    try:
        first_state = _get_login_state()
        monkeypatch.setitem(PROVIDERS, "google", fake_provider)
        first = client.get(
            "/auth/google/callback", params={"code": "fake-code-1", "state": first_state}
        )
        assert first.status_code == 200

        second_state = _get_login_state()
        monkeypatch.setitem(PROVIDERS, "google", fake_provider)
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
    state = _get_login_state()
    monkeypatch.setitem(
        PROVIDERS,
        "google",
        FakeOAuthProvider(name="google", result=UnauthorizedError("Google sign-in failed.")),
    )

    response = client.get("/auth/google/callback", params={"code": "bad-code", "state": state})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_second_provider_works_through_the_same_generic_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves the abstraction is real, not just a rename: a provider that
    was never hardcoded anywhere in routers/oauth.py works end-to-end
    purely by being registered in PROVIDERS — no route, no if/elif on
    provider name, nothing else changes."""
    email = "endpoint-test-oauth-github@example.com"
    monkeypatch.setitem(
        PROVIDERS,
        "github",
        FakeOAuthProvider(
            name="github",
            result=OAuthUserInfo(
                subject="github-subject-1", email=email, email_verified=True, full_name="Githubber"
            ),
        ),
    )

    try:
        state = _get_login_state(provider="github")
        response = client.get("/auth/github/callback", params={"code": "fake-code", "state": state})
        assert response.status_code == 200

        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one()
            identity_result = await session.execute(
                select(OAuthIdentity).where(OAuthIdentity.user_id == user.id)
            )
            identity = identity_result.scalar_one()
            assert identity.provider == "github"
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_signup_and_login_still_works_after_oauth_router_registered() -> None:
    """Not really an OAuth test — a cheap sanity check that adding a
    second router under /auth/* (oauth.router's prefix is /auth/{provider},
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
