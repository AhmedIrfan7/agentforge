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
from errors import UnauthorizedError

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
