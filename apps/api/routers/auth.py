"""Signup/login/session endpoints.

No RBAC/tenant concern here — signup creates a User (global identity),
not scoped to any organization yet. Joining an organization happens
through the invitation flow (roadmap steps 073-075) or by creating one
(routers/organization.py), both later.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import create_access_token, generate_refresh_token
from auth.passwords import hash_password, needs_rehash, verify_password
from dependencies.db import get_db
from errors import ConflictError, UnauthorizedError
from repositories.session import SessionRepository
from repositories.user import UserRepository
from schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserRead, status_code=201)
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
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(body.email)

    # Same error for "no such user" and "wrong password" — distinguishing
    # them lets an attacker enumerate valid emails (AGENTS.md SECTION 9).
    invalid_credentials = UnauthorizedError("Invalid email or password.")
    if user is None or user.hashed_password is None:
        raise invalid_credentials
    if not verify_password(body.password, user.hashed_password):
        raise invalid_credentials

    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(body.password)

    access_token = create_access_token(user.id)
    raw_refresh_token, refresh_token_hash, expires_at = generate_refresh_token()

    session_repo = SessionRepository(session)
    await session_repo.create(
        user_id=user.id,
        refresh_token_hash=refresh_token_hash,
        expires_at=expires_at,
        device_info=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh_token)
