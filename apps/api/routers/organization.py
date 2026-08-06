"""Organization CRUD, now with real access control (roadmap steps 070-072):

- Create: any authenticated user — there's no membership to check yet
  for an org that doesn't exist. The creator becomes org_owner
  automatically.
- List: only organizations the caller has a membership in (see
  repositories/organization.py:list_for_user and db.py:set_user_context
  for why this needs a second RLS policy, not just tenant context).
- Get/Delete: require membership in that specific org (get_tenant_db)
  plus the matching permission (require_permission).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from db import set_tenant_context, set_user_context
from dependencies.auth import get_current_user_id
from dependencies.db import get_db
from dependencies.rbac import require_permission
from dependencies.tenant import get_tenant_db
from errors import AppError, ConflictError, NotFoundError
from models.membership import Membership
from repositories.organization import OrganizationRepository
from repositories.role import RoleRepository
from schemas.common import Page, PaginationParams
from schemas.organization import OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
) -> OrganizationRead:
    repo = OrganizationRepository(session)
    try:
        org = await repo.create(name=body.name, slug=body.slug)
    except IntegrityError as exc:
        raise ConflictError(f"An organization with slug '{body.slug}' already exists.") from exc

    await set_tenant_context(session, org.id)

    owner_role = await RoleRepository(session).get_by_name("org_owner")
    if owner_role is None:
        # Only possible if the built-in role seed (migration a870af57e4d3)
        # never ran — a broken deployment, not a bad request.
        raise AppError("Built-in roles are not seeded; cannot assign an owner.")
    session.add(
        Membership(tenant_id=org.id, user_id=user_id, workspace_id=None, role_id=owner_role.id)
    )
    await session.flush()

    await write_audit_log(
        session,
        tenant_id=org.id,
        action="organization.create",
        resource_type="organization",
        resource_id=org.id,
        actor_user_id=user_id,
    )
    return OrganizationRead.model_validate(org)


@router.get("", response_model=Page[OrganizationRead])
async def list_organizations(
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    pagination: Annotated[PaginationParams, Depends()],
) -> Page[OrganizationRead]:
    await set_user_context(session, user_id)
    repo = OrganizationRepository(session)
    orgs = await repo.list_for_user(user_id, limit=pagination.limit, offset=pagination.offset)
    total = await repo.count_for_user(user_id)
    return Page(
        items=[OrganizationRead.model_validate(o) for o in orgs],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.get(
    "/{organization_id}",
    response_model=OrganizationRead,
    dependencies=[Depends(require_permission("organization:read"))],
)
async def get_organization(
    organization_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_tenant_db)]
) -> OrganizationRead:
    repo = OrganizationRepository(session)
    org = await repo.get(organization_id)
    if org is None:
        raise NotFoundError(f"Organization {organization_id} not found.")
    return OrganizationRead.model_validate(org)


@router.delete(
    "/{organization_id}",
    status_code=204,
    dependencies=[Depends(require_permission("organization:delete"))],
)
async def delete_organization(
    organization_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_tenant_db)],
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
) -> None:
    repo = OrganizationRepository(session)
    org = await repo.get(organization_id)
    if org is None:
        raise NotFoundError(f"Organization {organization_id} not found.")

    await write_audit_log(
        session,
        tenant_id=org.id,
        action="organization.delete",
        resource_type="organization",
        resource_id=org.id,
        actor_user_id=user_id,
    )
    await repo.delete(org)
