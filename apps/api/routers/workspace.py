"""Workspace CRUD, nested under an organization
(/organizations/{organization_id}/workspaces) so get_current_tenant_id
(dependencies/tenant.py) has an organization_id to resolve tenant
context from and verify membership against — this was flat /workspaces
until RBAC (roadmap steps 070-072) needed an unambiguous tenant source.

Each route depends on both get_tenant_db and get_current_tenant_id
directly. FastAPI caches a dependency's result per request by default, so
get_current_tenant_id only actually runs once even though get_tenant_db
also depends on it internally — this just gets that same cached value
back out, cleaner than smuggling it through session.info.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import ConflictError, NotFoundError
from repositories.workspace import WorkspaceRepository
from schemas.common import Page, PaginationParams
from schemas.workspace import WorkspaceCreate, WorkspaceRead

router = APIRouter(prefix="/organizations/{organization_id}/workspaces", tags=["workspaces"])

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]


@router.post(
    "",
    response_model=WorkspaceRead,
    status_code=201,
    dependencies=[Depends(require_permission("workspace:create"))],
)
async def create_workspace(
    body: WorkspaceCreate, session: TenantDb, tenant_id: TenantId
) -> WorkspaceRead:
    repo = WorkspaceRepository(session, tenant_id)
    try:
        workspace = await repo.create(name=body.name, slug=body.slug)
    except IntegrityError as exc:
        raise ConflictError(f"A workspace with slug '{body.slug}' already exists.") from exc

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="workspace.create",
        resource_type="workspace",
        resource_id=workspace.id,
    )
    return WorkspaceRead.model_validate(workspace)


@router.get(
    "",
    response_model=Page[WorkspaceRead],
    dependencies=[Depends(require_permission("workspace:read"))],
)
async def list_workspaces(
    session: TenantDb, tenant_id: TenantId, pagination: Annotated[PaginationParams, Depends()]
) -> Page[WorkspaceRead]:
    repo = WorkspaceRepository(session, tenant_id)
    workspaces = await repo.list(limit=pagination.limit, offset=pagination.offset)
    total = await repo.count()
    return Page(
        items=[WorkspaceRead.model_validate(w) for w in workspaces],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    dependencies=[Depends(require_permission("workspace:read"))],
)
async def get_workspace(
    workspace_id: uuid.UUID, session: TenantDb, tenant_id: TenantId
) -> WorkspaceRead:
    repo = WorkspaceRepository(session, tenant_id)
    workspace = await repo.get(workspace_id)
    if workspace is None:
        raise NotFoundError(f"Workspace {workspace_id} not found.")
    return WorkspaceRead.model_validate(workspace)


@router.delete(
    "/{workspace_id}",
    status_code=204,
    dependencies=[Depends(require_permission("workspace:delete"))],
)
async def delete_workspace(workspace_id: uuid.UUID, session: TenantDb, tenant_id: TenantId) -> None:
    repo = WorkspaceRepository(session, tenant_id)
    workspace = await repo.get(workspace_id)
    if workspace is None:
        raise NotFoundError(f"Workspace {workspace_id} not found.")

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="workspace.delete",
        resource_type="workspace",
        resource_id=workspace.id,
    )
    await repo.delete(workspace)
