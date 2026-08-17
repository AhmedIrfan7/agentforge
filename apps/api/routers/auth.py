"""Signup/login/session endpoints.

No RBAC/tenant concern here — signup creates a User (global identity),
not scoped to any organization yet. Joining an organization happens
through the invitation flow (roadmap steps 073-075) or by creating one
(routers/organization.py), both later.

As of step 255, a failed login attempt logs a real structured
"login_failed" event (AGENTS.md's own "AUDIT LOGGING" section names
"Authentication" failures by name) -- via structlog, not AuditLog: a
failed login has no real organization/tenant context yet (the caller
hasn't proven who they are, let alone which org they're acting within),
the identical mismatch every other tenant-scoped table in this codebase
would have with a genuinely global event. AuditLog's own real per-org
viewer (routers/audit_log.py, step 247) is reached through an
organization_id in the URL, which a pre-auth failure can never supply.
Both real failure branches below (no such user, wrong password) log
the identical event shape -- the same "don't let a defender-facing
signal leak what the client-facing error message already deliberately
doesn't" reasoning `invalid_credentials` below already applies to the
HTTP response.

As of step 259, both branches also call
`rate_limit.py:record_failed_login_attempt` -- genuinely distinct from
this same route's own `rate_limit(key_prefix="login", ...)` dependency
above (which caps volume per client IP): this tracks failures per
EMAIL, so it still catches a slow, distributed credential-stuffing
attempt against one specific account spread across many different IPs,
each individually well under the per-IP cap. See rate_limit.py's own
docstring for the full reasoning.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import (
    create_access_token,
    create_mfa_ticket,
    generate_refresh_token,
    hash_refresh_token,
)
from auth.passwords import hash_password, needs_rehash, verify_password
from auth.verification import generate_verification_token, hash_verification_token
from config import settings
from dependencies.auth import get_current_user_id
from dependencies.db import get_db
from errors import ConflictError, UnauthorizedError
from logging_config import get_logger
from models.user import User
from notifications.email import send_email
from rate_limit import rate_limit, record_failed_login_attempt
from repositories.session import SessionRepository
from repositories.user import UserRepository
from repositories.verification_token import VerificationTokenRepository
from schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MagicLinkRequest,
    MagicLinkVerifyRequest,
    MfaRequiredResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UserRead,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


async def issue_tokens(
    session: AsyncSession, user_id: uuid.UUID, request: Request
) -> TokenResponse:
    """Mints real tokens unconditionally — used by refresh rotation
    (which never re-checks MFA; the original login already did) and by
    complete_login below once MFA is either satisfied or not required."""
    access_token = create_access_token(user_id)
    raw_refresh_token, refresh_token_hash, expires_at = generate_refresh_token()

    session_repo = SessionRepository(session)
    await session_repo.create(
        user_id=user_id,
        refresh_token_hash=refresh_token_hash,
        expires_at=expires_at,
        device_info=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh_token)


async def complete_login(
    session: AsyncSession, user: User, request: Request
) -> TokenResponse | MfaRequiredResponse:
    """The shared "first factor just succeeded" completion point for
    password login, magic-link verify, and Google OAuth
    (routers/oauth.py) — refresh rotation does NOT go through this, since
    MFA already gated whichever login originally issued the refresh
    token. If MFA is enabled, hands back a short-lived ticket instead of
    real tokens; POST /auth/mfa/verify (routers/mfa.py) redeems it for
    the real ones after checking the second factor."""
    if user.mfa_enabled:
        return MfaRequiredResponse(mfa_ticket=create_mfa_ticket(user.id))
    return await issue_tokens(session, user.id, request)


async def _send_verification_email(session: AsyncSession, user_id: uuid.UUID, email: str) -> None:
    raw_token, token_hash, expires_at = generate_verification_token()
    await VerificationTokenRepository(session).create(
        user_id=user_id, token_hash=token_hash, purpose="email_verify", expires_at=expires_at
    )
    link = f"{settings.app_base_url}/verify-email?token={raw_token}"
    send_email(
        to=email,
        subject="Verify your AgentForge email",
        body=f"Click to verify your email: {link}\n\nThis link expires in 1 hour.",
    )


@router.post(
    "/signup",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(rate_limit(key_prefix="signup", limit=5, window_seconds=3600))],
)
async def signup(
    body: SignupRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> UserRead:
    repo = UserRepository(session)
    try:
        user = await repo.create(
            email=body.email,
            full_name=body.full_name,
            hashed_password=hash_password(body.password),
        )
    except IntegrityError as exc:
        raise ConflictError(f"An account with email '{body.email}' already exists.") from exc

    await _send_verification_email(session, user.id, user.email)
    return UserRead.model_validate(user)


@router.get("/me", response_model=UserRead)
async def get_me(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    user = await UserRepository(session).get(user_id)
    if user is None:
        raise UnauthorizedError("Invalid or expired token.")
    return UserRead.model_validate(user)


@router.post(
    "/verify-email",
    status_code=204,
    dependencies=[Depends(rate_limit(key_prefix="verify-email", limit=20, window_seconds=3600))],
)
async def verify_email(
    body: VerifyEmailRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    token_repo = VerificationTokenRepository(session)
    token_hash = hash_verification_token(body.token)
    token = await token_repo.get_valid(token_hash=token_hash, purpose="email_verify")

    invalid_token = UnauthorizedError("Invalid or expired verification token.")
    if token is None:
        raise invalid_token
    if token.used_at is not None:
        raise invalid_token
    if token.expires_at < datetime.now(UTC):
        raise invalid_token

    user = await UserRepository(session).get(token.user_id)
    if user is None:
        raise invalid_token

    user.is_email_verified = True
    await token_repo.mark_used(token)


@router.post(
    "/login",
    response_model=TokenResponse | MfaRequiredResponse,
    dependencies=[Depends(rate_limit(key_prefix="login", limit=10, window_seconds=300))],
)
async def login(
    body: LoginRequest, request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse | MfaRequiredResponse:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(body.email)
    client_ip = request.client.host if request.client else None

    # Same error for "no such user" and "wrong password" — distinguishing
    # them lets an attacker enumerate valid emails (AGENTS.md SECTION 9).
    invalid_credentials = UnauthorizedError("Invalid email or password.")
    if user is None or user.hashed_password is None:
        logger.warning("login_failed", email=body.email, ip=client_ip)
        await record_failed_login_attempt(body.email)
        raise invalid_credentials
    if not verify_password(body.password, user.hashed_password):
        logger.warning("login_failed", email=body.email, ip=client_ip)
        await record_failed_login_attempt(body.email)
        raise invalid_credentials

    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(body.password)

    return await complete_login(session, user, request)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(key_prefix="refresh", limit=30, window_seconds=300))],
)
async def refresh(
    body: RefreshRequest, request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    session_repo = SessionRepository(session)
    token_hash = hash_refresh_token(body.refresh_token)
    existing = await session_repo.get_by_refresh_token_hash(token_hash)

    invalid_token = UnauthorizedError("Invalid or expired refresh token.")
    if existing is None:
        raise invalid_token
    if existing.revoked_at is not None:
        raise invalid_token
    if existing.expires_at < datetime.now(UTC):
        raise invalid_token

    # Rotation: this refresh token is single-use. Revoking it here means a
    # stolen-and-already-used token can never be replayed — presenting it
    # again just looks like an already-revoked token (invalid_token above).
    await session_repo.revoke(existing)

    return await issue_tokens(session, existing.user_id, request)


@router.post(
    "/logout",
    status_code=204,
    dependencies=[Depends(rate_limit(key_prefix="logout", limit=30, window_seconds=300))],
)
async def logout(body: LogoutRequest, session: Annotated[AsyncSession, Depends(get_db)]) -> None:
    # Idempotent and silent either way: whether the token was valid,
    # already revoked, or never existed, logout looks the same to the
    # caller — no reason to leak which (AGENTS.md SECTION 9).
    session_repo = SessionRepository(session)
    token_hash = hash_refresh_token(body.refresh_token)
    existing = await session_repo.get_by_refresh_token_hash(token_hash)
    if existing is not None and existing.revoked_at is None:
        await session_repo.revoke(existing)


@router.post(
    "/magic-link/request",
    status_code=204,
    dependencies=[
        Depends(rate_limit(key_prefix="magic-link-request", limit=3, window_seconds=3600))
    ],
)
async def request_magic_link(
    body: MagicLinkRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    # Always 204 regardless of whether the email exists — a differing
    # response would let an attacker enumerate accounts (AGENTS.md
    # SECTION 9), same reasoning as login's identical invalid-credentials
    # message.
    user = await UserRepository(session).get_by_email(body.email)
    if user is None:
        return

    raw_token, token_hash, expires_at = generate_verification_token()
    await VerificationTokenRepository(session).create(
        user_id=user.id, token_hash=token_hash, purpose="magic_link", expires_at=expires_at
    )
    link = f"{settings.app_base_url}/magic-link?token={raw_token}"
    send_email(
        to=user.email,
        subject="Your AgentForge sign-in link",
        body=f"Click to sign in: {link}\n\nThis link expires in 1 hour.",
    )


@router.post(
    "/magic-link/verify",
    response_model=TokenResponse | MfaRequiredResponse,
    dependencies=[
        Depends(rate_limit(key_prefix="magic-link-verify", limit=20, window_seconds=3600))
    ],
)
async def verify_magic_link(
    body: MagicLinkVerifyRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse | MfaRequiredResponse:
    token_repo = VerificationTokenRepository(session)
    token_hash = hash_verification_token(body.token)
    token = await token_repo.get_valid(token_hash=token_hash, purpose="magic_link")

    invalid_token = UnauthorizedError("Invalid or expired sign-in link.")
    if token is None:
        raise invalid_token
    if token.used_at is not None:
        raise invalid_token
    if token.expires_at < datetime.now(UTC):
        raise invalid_token

    user = await UserRepository(session).get(token.user_id)
    if user is None:
        raise invalid_token

    await token_repo.mark_used(token)
    return await complete_login(session, user, request)


@router.post(
    "/password-reset/request",
    status_code=204,
    dependencies=[
        Depends(rate_limit(key_prefix="password-reset-request", limit=3, window_seconds=3600))
    ],
)
async def request_password_reset(
    body: PasswordResetRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    # Same anti-enumeration reasoning as magic-link/request.
    user = await UserRepository(session).get_by_email(body.email)
    if user is None:
        return

    raw_token, token_hash, expires_at = generate_verification_token()
    await VerificationTokenRepository(session).create(
        user_id=user.id, token_hash=token_hash, purpose="password_reset", expires_at=expires_at
    )
    link = f"{settings.app_base_url}/reset-password?token={raw_token}"
    send_email(
        to=user.email,
        subject="Reset your AgentForge password",
        body=f"Click to reset your password: {link}\n\nThis link expires in 1 hour.",
    )


@router.post(
    "/password-reset/confirm",
    status_code=204,
    dependencies=[
        Depends(rate_limit(key_prefix="password-reset-confirm", limit=20, window_seconds=3600))
    ],
)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    token_repo = VerificationTokenRepository(session)
    token_hash = hash_verification_token(body.token)
    token = await token_repo.get_valid(token_hash=token_hash, purpose="password_reset")

    invalid_token = UnauthorizedError("Invalid or expired password reset link.")
    if token is None:
        raise invalid_token
    if token.used_at is not None:
        raise invalid_token
    if token.expires_at < datetime.now(UTC):
        raise invalid_token

    user = await UserRepository(session).get(token.user_id)
    if user is None:
        raise invalid_token

    user.hashed_password = hash_password(body.new_password)
    await token_repo.mark_used(token)

    # If the account was compromised, any already-logged-in session could
    # be the attacker's, not the real owner's — a reset invalidates all
    # of them, not just the password going forward.
    await SessionRepository(session).revoke_all_for_user(user.id)
