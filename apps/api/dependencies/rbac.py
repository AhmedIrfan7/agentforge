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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, set_tenant_context
from dependencies.auth import get_current_user_id
from dependencies.tenant import get_current_tenant_id
from errors import ForbiddenError
from models.role import Role
from repositories.rbac import get_user_memberships, get_user_permissions

ORG_OWNER_ROLE_NAME = "org_owner"


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


async def require_org_owner(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Raises ForbiddenError unless the caller holds the org_owner role
    within this tenant -- the same carve-out organization:delete (234)
    established on top of a broader permission tier, shared by every
    later endpoint that needs it too: membership role changes touching
    org_owner (239) and inviting someone directly as org_owner (240).
    Assigning the org_owner role should never be reachable by anyone
    who isn't already one, regardless of which door (a direct role
    change or an invitation) it comes through."""
    memberships = await get_user_memberships(session, user_id=user_id, tenant_id=tenant_id)
    role_ids = {m.role_id for m in memberships}
    role_names: set[str] = set()
    if role_ids:
        result = await session.execute(select(Role.name).where(Role.id.in_(role_ids)))
        role_names = set(result.scalars().all())
    if ORG_OWNER_ROLE_NAME not in role_names:
        raise ForbiddenError("Only an organization owner can do this.")
