"""Workspace CRUD, tenant-scoped via dependencies/tenant.py:get_tenant_db.

Non-functional until Milestone 2's auth exists (roadmap steps 060-062):
get_tenant_db depends on get_current_tenant_id, which currently raises
NotImplementedError — see dependencies/tenant.py. That's intentional;
these routes are wired correctly and will start working the moment real
tenant resolution lands, with no route code changes needed.

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
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import ConflictError, NotFoundError
from repositories.workspace import WorkspaceRepository
from schemas.common import Page, PaginationParams
from schemas.workspace import WorkspaceCreate, WorkspaceRead

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]


@router.post("", response_model=WorkspaceRead, status_code=201)
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


@router.get("", response_model=Page[WorkspaceRead])
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


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: uuid.UUID, session: TenantDb, tenant_id: TenantId
) -> WorkspaceRead:
    repo = WorkspaceRepository(session, tenant_id)
    workspace = await repo.get(workspace_id)
    if workspace is None:
        raise NotFoundError(f"Workspace {workspace_id} not found.")
    return WorkspaceRead.model_validate(workspace)


@router.delete("/{workspace_id}", status_code=204)
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
