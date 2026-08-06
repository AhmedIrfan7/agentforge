"""Signup/login/session endpoints.

No RBAC/tenant concern here — signup creates a User (global identity),
not scoped to any organization yet. Joining an organization happens
through the invitation flow (roadmap steps 073-075) or by creating one
(routers/organization.py), both later.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.passwords import hash_password
from dependencies.db import get_db
from errors import ConflictError
from repositories.user import UserRepository
from schemas.auth import SignupRequest, UserRead

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
