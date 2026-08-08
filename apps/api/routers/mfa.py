"""MFA/TOTP enrollment, confirmation, disable, and login-completion
(roadmap step 078).

/enroll, /confirm, and /disable all require a real access token — MFA is
managed from within an already-authenticated session, not during login.
/verify is the opposite: it deliberately does NOT require a real access
token, only the mfa_ticket routers/auth.py:login (or magic-link verify,
or routers/oauth.py:oauth_callback) issues instead of real tokens when
mfa_enabled is true — that ticket alone proves the first factor already
succeeded, and this endpoint's whole job is checking the second one
before finally calling issue_tokens.

/verify is rate-limited the same way login/refresh/magic-link-verify
are, and for the same reason: it's reachable before full authentication,
which every other pre-auth endpoint in routers/auth.py already treats as
a brute-force target. /enroll, /confirm, and /disable sit behind a real
access token already, matching how every other authenticated-only route
in this codebase (organization/workspace/invitation CRUD) isn't
rate-limited on top of that.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import TokenError, decode_mfa_ticket
from auth.mfa import (
    build_provisioning_uri,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_backup_codes,
    generate_totp_secret,
    verify_backup_code,
    verify_totp_code,
)
from auth.passwords import verify_password
from dependencies.auth import get_current_user_id
from dependencies.db import get_db
from errors import ConflictError, UnauthorizedError
from rate_limit import rate_limit
from repositories.mfa_backup_code import MfaBackupCodeRepository
from repositories.user import UserRepository
from routers.auth import issue_tokens
from schemas.auth import (
    MfaConfirmRequest,
    MfaConfirmResponse,
    MfaDisableRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth/mfa", tags=["auth"])

CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/enroll", response_model=MfaEnrollResponse)
async def enroll_mfa(session: Db, user_id: CurrentUserId) -> MfaEnrollResponse:
    user_repo = UserRepository(session)
    user = await user_repo.get(user_id)
    if user is None:
        raise UnauthorizedError("Invalid or expired token.")
    if user.mfa_enabled:
        raise ConflictError("MFA is already enabled on this account.")

    secret = generate_totp_secret()
    user.mfa_totp_secret_encrypted = encrypt_totp_secret(secret)

    return MfaEnrollResponse(secret=secret, otpauth_uri=build_provisioning_uri(secret, user.email))


@router.post("/confirm", response_model=MfaConfirmResponse)
async def confirm_mfa(
    body: MfaConfirmRequest, session: Db, user_id: CurrentUserId
) -> MfaConfirmResponse:
    user = await UserRepository(session).get(user_id)
    if user is None or user.mfa_totp_secret_encrypted is None:
        raise ConflictError("No pending MFA enrollment to confirm — call /enroll first.")

    secret = decrypt_totp_secret(user.mfa_totp_secret_encrypted)
    if secret is None or not verify_totp_code(secret, body.code):
        raise UnauthorizedError("Invalid MFA code.")

    user.mfa_enabled = True
    backup_codes = generate_backup_codes()
    await MfaBackupCodeRepository(session).create_many(user_id=user.id, hashes=backup_codes.hashes)

    return MfaConfirmResponse(backup_codes=backup_codes.raw_codes)


@router.post("/disable", status_code=204)
async def disable_mfa(body: MfaDisableRequest, session: Db, user_id: CurrentUserId) -> None:
    user = await UserRepository(session).get(user_id)
    if user is None or not user.mfa_enabled:
        raise ConflictError("MFA is not enabled on this account.")

    proven = False
    if body.password is not None and user.hashed_password is not None:
        proven = verify_password(body.password, user.hashed_password)
    if not proven and body.code is not None and user.mfa_totp_secret_encrypted is not None:
        secret = decrypt_totp_secret(user.mfa_totp_secret_encrypted)
        proven = secret is not None and verify_totp_code(secret, body.code)

    if not proven:
        raise UnauthorizedError("Incorrect password or code.")

    user.mfa_enabled = False
    user.mfa_totp_secret_encrypted = None
    await MfaBackupCodeRepository(session).delete_all_for_user(user.id)


@router.post(
    "/verify",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit(key_prefix="mfa-verify", limit=10, window_seconds=900))],
)
async def verify_mfa(body: MfaVerifyRequest, request: Request, session: Db) -> TokenResponse:
    invalid_attempt = UnauthorizedError("Invalid or expired sign-in attempt.")
    try:
        user_id = decode_mfa_ticket(body.mfa_ticket)
    except TokenError as exc:
        raise invalid_attempt from exc

    user = await UserRepository(session).get(user_id)
    if user is None or not user.mfa_enabled or user.mfa_totp_secret_encrypted is None:
        raise invalid_attempt

    secret = decrypt_totp_secret(user.mfa_totp_secret_encrypted)
    if secret is not None and verify_totp_code(secret, body.code):
        return await issue_tokens(session, user.id, request)

    backup_repo = MfaBackupCodeRepository(session)
    for candidate in await backup_repo.list_unused(user.id):
        if verify_backup_code(body.code, candidate.code_hash):
            candidate.used_at = datetime.now(UTC)
            return await issue_tokens(session, user.id, request)

    raise UnauthorizedError("Invalid MFA code.")
