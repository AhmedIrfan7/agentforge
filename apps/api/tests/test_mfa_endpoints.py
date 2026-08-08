"""Integration tests against the real FastAPI app for routers/mfa.py
(roadmap step 078), and the mfa_enabled gate added to login/magic-link
verify/Google OAuth in routers/auth.py and routers/oauth.py.
"""

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session
from main import app
from models.mfa_backup_code import MfaBackupCode
from models.session import Session
from models.user import User
from tests.helpers import auth_headers, signup_and_login

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
        backup_result = await session.execute(
            select(MfaBackupCode).where(MfaBackupCode.user_id == user.id)
        )
        for code in backup_result.scalars().all():
            await session.delete(code)
        await session.delete(user)
        await session.commit()


def _enroll_and_confirm(headers: dict[str, str]) -> tuple[str, list[str]]:
    """Runs the real enroll -> confirm flow through the actual endpoints
    and returns (totp_secret, backup_codes) — the secret so tests can
    generate real, valid codes with pyotp exactly like an authenticator
    app would, not a stub."""
    enroll = client.post("/auth/mfa/enroll", headers=headers)
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]

    code = pyotp.TOTP(secret).now()
    confirm = client.post("/auth/mfa/confirm", json={"code": code}, headers=headers)
    assert confirm.status_code == 200
    backup_codes: list[str] = confirm.json()["backup_codes"]
    return secret, backup_codes


def test_enroll_requires_auth() -> None:
    response = client.post("/auth/mfa/enroll")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_enroll_returns_secret_pending_not_yet_enabled() -> None:
    email = "endpoint-test-mfa-enroll-1@example.com"
    try:
        token = signup_and_login(
            client, email=email, password="correct horse battery staple", full_name="Enroller"
        )
        headers = auth_headers(token)

        response = client.post("/auth/mfa/enroll", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert "secret" in body
        assert body["otpauth_uri"].startswith("otpauth://totp/")

        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one()
            assert user.mfa_totp_secret_encrypted is not None
            assert user.mfa_enabled is False
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_confirm_without_enrollment_returns_409() -> None:
    email = "endpoint-test-mfa-confirm-noenroll@example.com"
    try:
        token = signup_and_login(
            client, email=email, password="correct horse battery staple", full_name="NoEnroll"
        )
        response = client.post(
            "/auth/mfa/confirm", json={"code": "123456"}, headers=auth_headers(token)
        )
        assert response.status_code == 409
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_confirm_with_wrong_code_returns_401() -> None:
    email = "endpoint-test-mfa-confirm-wrong@example.com"
    try:
        token = signup_and_login(
            client, email=email, password="correct horse battery staple", full_name="WrongCode"
        )
        headers = auth_headers(token)
        client.post("/auth/mfa/enroll", headers=headers)

        response = client.post("/auth/mfa/confirm", json={"code": "000000"}, headers=headers)
        assert response.status_code == 401
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_confirm_with_correct_code_enables_mfa_and_returns_ten_backup_codes() -> None:
    email = "endpoint-test-mfa-confirm-ok@example.com"
    try:
        token = signup_and_login(
            client, email=email, password="correct horse battery staple", full_name="Confirmer"
        )
        headers = auth_headers(token)
        _secret, backup_codes = _enroll_and_confirm(headers)

        assert len(backup_codes) == 10
        assert len(set(backup_codes)) == 10  # all distinct

        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one()
            assert user.mfa_enabled is True

            code_result = await session.execute(
                select(MfaBackupCode).where(MfaBackupCode.user_id == user.id)
            )
            codes = code_result.scalars().all()
            assert len(codes) == 10
            assert all(c.used_at is None for c in codes)
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_enroll_when_already_enabled_returns_409() -> None:
    email = "endpoint-test-mfa-enroll-twice@example.com"
    try:
        token = signup_and_login(
            client, email=email, password="correct horse battery staple", full_name="Twice"
        )
        headers = auth_headers(token)
        _enroll_and_confirm(headers)

        response = client.post("/auth/mfa/enroll", headers=headers)
        assert response.status_code == 409
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_login_with_mfa_enabled_returns_ticket_not_tokens() -> None:
    email = "endpoint-test-mfa-login-1@example.com"
    password = "correct horse battery staple"
    try:
        token = signup_and_login(client, email=email, password=password, full_name="Logger")
        _enroll_and_confirm(auth_headers(token))

        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200
        body = response.json()
        assert body.get("mfa_required") is True
        assert "mfa_ticket" in body
        assert "access_token" not in body
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_mfa_verify_with_totp_code_completes_login() -> None:
    email = "endpoint-test-mfa-verify-totp@example.com"
    password = "correct horse battery staple"
    try:
        token = signup_and_login(client, email=email, password=password, full_name="Verifier")
        secret, _backup_codes = _enroll_and_confirm(auth_headers(token))

        login_response = client.post("/auth/login", json={"email": email, "password": password})
        ticket = login_response.json()["mfa_ticket"]

        code = pyotp.TOTP(secret).now()
        verify_response = client.post("/auth/mfa/verify", json={"mfa_ticket": ticket, "code": code})
        assert verify_response.status_code == 200
        body = verify_response.json()
        assert "access_token" in body
        assert "refresh_token" in body
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_mfa_verify_with_backup_code_completes_login_and_consumes_it() -> None:
    email = "endpoint-test-mfa-verify-backup@example.com"
    password = "correct horse battery staple"
    try:
        token = signup_and_login(client, email=email, password=password, full_name="Backup")
        _secret, backup_codes = _enroll_and_confirm(auth_headers(token))
        one_time_code = backup_codes[0]

        login_response = client.post("/auth/login", json={"email": email, "password": password})
        ticket = login_response.json()["mfa_ticket"]

        first = client.post("/auth/mfa/verify", json={"mfa_ticket": ticket, "code": one_time_code})
        assert first.status_code == 200

        # Single-use: the same backup code must not work a second time,
        # even against a fresh ticket.
        second_login = client.post("/auth/login", json={"email": email, "password": password})
        second_ticket = second_login.json()["mfa_ticket"]
        second = client.post(
            "/auth/mfa/verify", json={"mfa_ticket": second_ticket, "code": one_time_code}
        )
        assert second.status_code == 401
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_mfa_verify_with_wrong_code_returns_401() -> None:
    email = "endpoint-test-mfa-verify-wrong@example.com"
    password = "correct horse battery staple"
    try:
        token = signup_and_login(client, email=email, password=password, full_name="WrongVerify")
        _enroll_and_confirm(auth_headers(token))

        login_response = client.post("/auth/login", json={"email": email, "password": password})
        ticket = login_response.json()["mfa_ticket"]

        response = client.post("/auth/mfa/verify", json={"mfa_ticket": ticket, "code": "000000"})
        assert response.status_code == 401
    finally:
        await _cleanup_user(email)


def test_mfa_verify_with_garbage_ticket_returns_401() -> None:
    response = client.post(
        "/auth/mfa/verify", json={"mfa_ticket": "not-a-real-ticket", "code": "123456"}
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_mfa_ticket_cannot_be_used_as_access_token() -> None:
    email = "endpoint-test-mfa-ticket-scope@example.com"
    password = "correct horse battery staple"
    try:
        token = signup_and_login(client, email=email, password=password, full_name="Scoped")
        _enroll_and_confirm(auth_headers(token))

        login_response = client.post("/auth/login", json={"email": email, "password": password})
        ticket = login_response.json()["mfa_ticket"]

        # The mfa_ticket is a different JWT `type` than an access token
        # (auth/jwt.py) — it must not work as a bearer credential for
        # anything else, including MFA's own enroll/disable endpoints.
        response = client.post("/auth/mfa/disable", json={}, headers=auth_headers(ticket))
        assert response.status_code == 401
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_disable_requires_correct_password_or_code() -> None:
    email = "endpoint-test-mfa-disable-1@example.com"
    password = "correct horse battery staple"
    try:
        token = signup_and_login(client, email=email, password=password, full_name="Disabler")
        headers = auth_headers(token)
        _enroll_and_confirm(headers)

        wrong = client.post(
            "/auth/mfa/disable", json={"password": "totally-wrong"}, headers=headers
        )
        assert wrong.status_code == 401

        correct = client.post("/auth/mfa/disable", json={"password": password}, headers=headers)
        assert correct.status_code == 204

        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one()
            assert user.mfa_enabled is False
            assert user.mfa_totp_secret_encrypted is None

            code_result = await session.execute(
                select(MfaBackupCode).where(MfaBackupCode.user_id == user.id)
            )
            assert code_result.scalars().all() == []
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_disable_when_not_enabled_returns_409() -> None:
    email = "endpoint-test-mfa-disable-notenabled@example.com"
    try:
        token = signup_and_login(
            client, email=email, password="correct horse battery staple", full_name="NeverOn"
        )
        response = client.post(
            "/auth/mfa/disable",
            json={"password": "correct horse battery staple"},
            headers=auth_headers(token),
        )
        assert response.status_code == 409
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_refresh_does_not_require_mfa_again() -> None:
    """Refresh continues an already-authenticated session — the original
    login already satisfied MFA to get the refresh token in the first
    place, so refresh must not re-gate on it."""
    email = "endpoint-test-mfa-refresh@example.com"
    password = "correct horse battery staple"
    try:
        token = signup_and_login(client, email=email, password=password, full_name="Refresher")
        secret, _backup_codes = _enroll_and_confirm(auth_headers(token))

        login_response = client.post("/auth/login", json={"email": email, "password": password})
        ticket = login_response.json()["mfa_ticket"]
        code = pyotp.TOTP(secret).now()
        verify_response = client.post("/auth/mfa/verify", json={"mfa_ticket": ticket, "code": code})
        refresh_token = verify_response.json()["refresh_token"]

        refresh_response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh_response.status_code == 200
        assert "access_token" in refresh_response.json()
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_magic_link_verify_respects_mfa() -> None:
    email = "endpoint-test-mfa-magiclink@example.com"
    password = "correct horse battery staple"
    try:
        token = signup_and_login(client, email=email, password=password, full_name="MagicMFA")
        _enroll_and_confirm(auth_headers(token))

        from auth.verification import generate_verification_token
        from repositories.verification_token import VerificationTokenRepository

        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one()
            raw_token, token_hash, expires_at = generate_verification_token()
            await VerificationTokenRepository(session).create(
                user_id=user.id, token_hash=token_hash, purpose="magic_link", expires_at=expires_at
            )
            await session.commit()

        response = client.post("/auth/magic-link/verify", json={"token": raw_token})
        assert response.status_code == 200
        body = response.json()
        assert body.get("mfa_required") is True
        assert "access_token" not in body
    finally:
        await _cleanup_user(email)
