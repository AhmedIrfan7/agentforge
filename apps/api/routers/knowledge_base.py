"""KnowledgeBase CRUD, nested two levels under organization
(/organizations/{organization_id}/workspaces/{workspace_id}/knowledge-bases)
matching the product hierarchy (AGENTS.md SECTION 3: org -> workspace ->
knowledge base -> ...). Same scope as routers/workspace.py: create,
list, get, delete -- no update endpoint, mirroring Workspace's own (it
doesn't have one either).

get_target_workspace cross-checks the URL's workspace_id against a real
Workspace row in this tenant before any route body runs -- same "path
param is a hint, not a trust boundary" reasoning as
dependencies/tenant.py's organization_id: a workspace_id belonging to a
different organization must 404, not silently succeed just because the
caller has *some* access to the outer organization_id.
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
from models.workspace import Workspace
from repositories.knowledge_base import KnowledgeBaseRepository
from repositories.workspace import WorkspaceRepository
from schemas.common import Page, PaginationParams
from schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseRead

router = APIRouter(
    prefix="/organizations/{organization_id}/workspaces/{workspace_id}/knowledge-bases",
    tags=["knowledge-bases"],
)

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]


async def get_target_workspace(
    workspace_id: uuid.UUID, session: TenantDb, tenant_id: TenantId
) -> Workspace:
    workspace = await WorkspaceRepository(session, tenant_id).get(workspace_id)
    if workspace is None:
        raise NotFoundError(f"Workspace {workspace_id} not found.")
    return workspace


TargetWorkspace = Annotated[Workspace, Depends(get_target_workspace)]


@router.post(
    "",
    response_model=KnowledgeBaseRead,
    status_code=201,
    dependencies=[Depends(require_permission("knowledge_base:create"))],
)
async def create_knowledge_base(
    body: KnowledgeBaseCreate, session: TenantDb, tenant_id: TenantId, workspace: TargetWorkspace
) -> KnowledgeBaseRead:
    repo = KnowledgeBaseRepository(session, tenant_id)
    try:
        knowledge_base = await repo.create(
            workspace_id=workspace.id, name=body.name, slug=body.slug, description=body.description
        )
    except IntegrityError as exc:
        raise ConflictError(
            f"A knowledge base with slug '{body.slug}' already exists in this workspace."
        ) from exc

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="knowledge_base.create",
        resource_type="knowledge_base",
        resource_id=knowledge_base.id,
    )
    return KnowledgeBaseRead.model_validate(knowledge_base)


@router.get(
    "",
    response_model=Page[KnowledgeBaseRead],
    dependencies=[Depends(require_permission("knowledge_base:read"))],
)
async def list_knowledge_bases(
    session: TenantDb,
    tenant_id: TenantId,
    workspace: TargetWorkspace,
    pagination: Annotated[PaginationParams, Depends()],
) -> Page[KnowledgeBaseRead]:
    repo = KnowledgeBaseRepository(session, tenant_id)
    knowledge_bases = await repo.list_for_workspace(
        workspace.id, limit=pagination.limit, offset=pagination.offset
    )
    total = await repo.count_for_workspace(workspace.id)
    return Page(
        items=[KnowledgeBaseRead.model_validate(kb) for kb in knowledge_bases],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.get(
    "/{knowledge_base_id}",
    response_model=KnowledgeBaseRead,
    dependencies=[Depends(require_permission("knowledge_base:read"))],
)
async def get_knowledge_base(
    knowledge_base_id: uuid.UUID, session: TenantDb, tenant_id: TenantId, workspace: TargetWorkspace
) -> KnowledgeBaseRead:
    repo = KnowledgeBaseRepository(session, tenant_id)
    knowledge_base = await repo.get(knowledge_base_id)
    if knowledge_base is None or knowledge_base.workspace_id != workspace.id:
        raise NotFoundError(f"Knowledge base {knowledge_base_id} not found.")
    return KnowledgeBaseRead.model_validate(knowledge_base)


@router.delete(
    "/{knowledge_base_id}",
    status_code=204,
    dependencies=[Depends(require_permission("knowledge_base:delete"))],
)
async def delete_knowledge_base(
    knowledge_base_id: uuid.UUID, session: TenantDb, tenant_id: TenantId, workspace: TargetWorkspace
) -> None:
    repo = KnowledgeBaseRepository(session, tenant_id)
    knowledge_base = await repo.get(knowledge_base_id)
    if knowledge_base is None or knowledge_base.workspace_id != workspace.id:
        raise NotFoundError(f"Knowledge base {knowledge_base_id} not found.")

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="knowledge_base.delete",
        resource_type="knowledge_base",
        resource_id=knowledge_base.id,
    )
    await repo.delete(knowledge_base)
