"""Read-side helpers for tenant membership + permission resolution.

Not a TenantScopedRepository: these queries run against the plain
(non-tenant-scoped) get_db session, BEFORE tenant context is
established — resolving whether a user belongs to a tenant is exactly
the step that has to happen before set_tenant_context() can run at all.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.membership import Membership
from models.permission import Permission, RolePermission


async def get_user_memberships(
    session: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[Membership]:
    """Every membership row (org-level and/or workspace-level — a user can
    have both) this user has within this specific organization."""
    result = await session.execute(
        select(Membership).where(Membership.user_id == user_id, Membership.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


async def get_user_permissions(
    session: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> set[str]:
    """Union of every permission granted by any of the user's roles within
    this organization — belonging via an org-level OR a workspace-level
    membership both count."""
    memberships = await get_user_memberships(session, user_id=user_id, tenant_id=tenant_id)
    if not memberships:
        return set()

    role_ids = {m.role_id for m in memberships}
    result = await session.execute(
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id.in_(role_ids))
    )
    return set(result.scalars().all())
