"""Org-member listing + role management (roadmap step 239).

Org-level membership only (workspace_id IS NULL) -- Membership's own
docstring already documents workspace-specific assignment as a real,
distinct concept this step doesn't touch; no roadmap step through 250
asks for a workspace-level member UI.

Two real business rules beyond plain RBAC, both existing to prevent an
organization ending up with zero owners or a non-owner silently
handing themselves owner-level control:
- Only an existing org_owner may assign the org_owner role to someone,
  or change/remove an EXISTING org_owner's membership -- same
  "org_owner-only carve-out on top of a broader tier" shape
  organization:delete already established (step 234).
- No update or delete may leave an organization with zero org_owner
  memberships.
Acting on your OWN membership through this admin endpoint is out of
scope -- "leave an organization" is a different, real feature no
roadmap step through 250 asks for; a self-service role change here
would just be a confusing shortcut around it.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from dependencies.auth import get_current_user_id
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import ConflictError, ForbiddenError, NotFoundError
from models.role import Role
from models.user import User
from repositories.membership import MembershipRepository
from repositories.rbac import get_user_memberships
from repositories.role import RoleRepository
from schemas.common import Page, PaginationParams
from schemas.membership import MembershipRead, MembershipUpdate

router = APIRouter(prefix="/organizations/{organization_id}/members", tags=["members"])

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]

ORG_OWNER_ROLE_NAME = "org_owner"


def _to_membership_read(
    membership_id: uuid.UUID, created_at: datetime, user: User, role: Role
) -> MembershipRead:
    return MembershipRead(
        id=membership_id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_id=role.id,
        role_name=role.name,
        role_display_name=role.display_name,
        created_at=created_at,
    )


async def _require_acting_org_owner(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    memberships = await get_user_memberships(session, user_id=user_id, tenant_id=tenant_id)
    role_ids = {m.role_id for m in memberships}
    role_names: set[str] = set()
    if role_ids:
        result = await session.execute(select(Role.name).where(Role.id.in_(role_ids)))
        role_names = set(result.scalars().all())
    if ORG_OWNER_ROLE_NAME not in role_names:
        raise ForbiddenError("Only an organization owner can do this.")


async def _ensure_not_last_owner(repo: MembershipRepository, org_owner_role_id: uuid.UUID) -> None:
    count = await repo.count_org_owners(org_owner_role_id)
    if count <= 1:
        raise ConflictError("An organization must have at least one owner.")


@router.get(
    "",
    response_model=Page[MembershipRead],
    dependencies=[Depends(require_permission("membership:read"))],
)
async def list_members(
    session: TenantDb, tenant_id: TenantId, pagination: Annotated[PaginationParams, Depends()]
) -> Page[MembershipRead]:
    repo = MembershipRepository(session, tenant_id)
    rows = await repo.list_org_level_with_user_and_role(
        limit=pagination.limit, offset=pagination.offset
    )
    total = await repo.count_org_level()
    return Page(
        items=[_to_membership_read(m.id, m.created_at, u, r) for m, u, r in rows],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.patch(
    "/{membership_id}",
    response_model=MembershipRead,
    dependencies=[Depends(require_permission("membership:update"))],
)
async def update_member_role(
    membership_id: uuid.UUID,
    body: MembershipUpdate,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: CurrentUserId,
) -> MembershipRead:
    repo = MembershipRepository(session, tenant_id)
    membership = await repo.get(membership_id)
    if membership is None or membership.workspace_id is not None:
        raise NotFoundError(f"Member {membership_id} not found.")
    if membership.user_id == user_id:
        raise ConflictError("You can't change your own role here.")

    new_role = await RoleRepository(session).get_by_name(body.role_name)
    if new_role is None:
        raise NotFoundError(f"Role '{body.role_name}' does not exist.")

    current_role = await session.get(Role, membership.role_id)
    current_is_owner = current_role is not None and current_role.name == ORG_OWNER_ROLE_NAME
    new_is_owner = new_role.name == ORG_OWNER_ROLE_NAME
    if current_is_owner or new_is_owner:
        await _require_acting_org_owner(session, tenant_id, user_id)
    if current_is_owner and not new_is_owner:
        await _ensure_not_last_owner(repo, current_role.id)  # type: ignore[union-attr]

    membership.role_id = new_role.id

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="membership.update_role",
        resource_type="membership",
        resource_id=membership.id,
        actor_user_id=user_id,
    )
    await session.refresh(membership)

    user = await session.get(User, membership.user_id)
    assert user is not None
    return _to_membership_read(membership.id, membership.created_at, user, new_role)


@router.delete(
    "/{membership_id}",
    status_code=204,
    dependencies=[Depends(require_permission("membership:delete"))],
)
async def remove_member(
    membership_id: uuid.UUID, session: TenantDb, tenant_id: TenantId, user_id: CurrentUserId
) -> None:
    repo = MembershipRepository(session, tenant_id)
    membership = await repo.get(membership_id)
    if membership is None or membership.workspace_id is not None:
        raise NotFoundError(f"Member {membership_id} not found.")
    if membership.user_id == user_id:
        raise ConflictError("You can't remove your own membership here.")

    current_role = await session.get(Role, membership.role_id)
    if current_role is not None and current_role.name == ORG_OWNER_ROLE_NAME:
        await _require_acting_org_owner(session, tenant_id, user_id)
        await _ensure_not_last_owner(repo, current_role.id)

    await repo.delete(membership)

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="membership.remove",
        resource_type="membership",
        resource_id=membership_id,
        actor_user_id=user_id,
    )
