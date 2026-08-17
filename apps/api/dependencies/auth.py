"""Authenticated-user resolution for FastAPI routes.

This is the JWT-decoding half dependencies/tenant.py's placeholder was
always waiting for (see that module's docstring, written back in step
044) — get_current_user_id here is what get_current_tenant_id finally
delegates to.
"""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.jwt import TokenError, decode_access_token
from db import get_session
from errors import ForbiddenError, UnauthorizedError
from models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> uuid.UUID:
    if credentials is None:
        raise UnauthorizedError("Missing or invalid Authorization header.")
    try:
        return decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired access token.") from exc


async def require_platform_admin(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
) -> None:
    """Gates platform-level (cross-tenant) views on User.is_platform_admin
    (models/user.py, models/role.py's own docstring: "Platform Super
    Admin... doesn't fit a per-org Membership role") -- the first real
    check of this field since it was seeded, and the same gate
    dependencies/db.py:get_db's own docstring already predicted for
    "future platform-admin cross-tenant views." Not dependencies/rbac.py:
    require_permission, deliberately -- that checks per-tenant Membership
    roles, and this data has no tenant to check one against."""
    async with get_session() as session:
        user = await session.get(User, user_id)
    if user is None or not user.is_platform_admin:
        raise ForbiddenError("Platform admin access required.")
