"""Per-route permission enforcement — the "072: enforce role checks per
route" half. require_permission(key) checks the union of permissions
granted by every role the current user holds within the current tenant
(repositories/rbac.py:get_user_permissions) — a user with both an
org-level and a workspace-level membership gets whichever permissions
either role grants, not just one.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends

from db import get_session, set_tenant_context
from dependencies.auth import get_current_user_id
from dependencies.tenant import get_current_tenant_id
from errors import ForbiddenError
from repositories.rbac import get_user_permissions


def require_permission(permission_key: str) -> Callable[..., Awaitable[None]]:
    async def dependency(
        tenant_id: Annotated[uuid.UUID, Depends(get_current_tenant_id)],
        user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    ) -> None:
        async with get_session() as session:
            # Same RLS gotcha as get_current_tenant_id: Membership/Permission
            # reads are blocked without a tenant context set on this session.
            await set_tenant_context(session, tenant_id)
            permissions = await get_user_permissions(session, user_id=user_id, tenant_id=tenant_id)
        if permission_key not in permissions:
            raise ForbiddenError(f"You do not have the '{permission_key}' permission.")

    return dependency
