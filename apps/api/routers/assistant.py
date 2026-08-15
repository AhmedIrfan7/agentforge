"""Assistant CRUD (roadmap step 160), nested three levels under
organization
(/organizations/{id}/workspaces/{id}/knowledge-bases/{id}/assistants)
matching the product hierarchy (AGENTS.md's "ORGANIZATION STRUCTURE":
org -> workspace -> knowledge base -> AI assistant -> ...), one level
deeper than routers/knowledge_base.py's own nesting. Same scope as
routers/knowledge_base.py/routers/workspace.py: create, list, get,
delete -- no update endpoint, mirroring both (neither has one either);
"CRUD" in this codebase's own usage has consistently meant this same
four-operation set, not literally requiring update, and a real update
endpoint would need its own design decision about partial vs. full
replacement of agent_configuration that nothing has asked for yet.

Reuses dependencies/knowledge_base.py:TargetKnowledgeBase directly --
the exact "resolve + cross-check the URL's knowledge_base_id against a
real row in this tenant/workspace" dependency routers/document.py and
routers/retrieval.py already share, not a new one-off copy.

request body's agent_configuration is a real agents/configuration.py:
AgentConfiguration (158), not a bare dict -- validated at the API
boundary before it ever reaches the JSONB column, same "validated
structure at the application layer" split that column's own docstring
promised. Stored via .model_dump() (the column itself is a plain
dict); read back via AssistantRead's own from_attributes handling,
which Pydantic v2 validates back into a real AgentConfiguration
automatically.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import ConflictError, NotFoundError
from repositories.assistant import AssistantRepository
from schemas.assistant import AssistantCreate, AssistantRead
from schemas.common import Page, PaginationParams

router = APIRouter(
    prefix=(
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}/assistants"
    ),
    tags=["assistants"],
)

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]


@router.post(
    "",
    response_model=AssistantRead,
    status_code=201,
    dependencies=[Depends(require_permission("assistant:create"))],
)
async def create_assistant(
    body: AssistantCreate,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> AssistantRead:
    repo = AssistantRepository(session, tenant_id)
    try:
        assistant = await repo.create(
            knowledge_base_id=knowledge_base.id,
            name=body.name,
            slug=body.slug,
            description=body.description,
            agent_configuration=body.agent_configuration.model_dump(),
            is_public=body.is_public,
        )
    except IntegrityError as exc:
        raise ConflictError(
            f"An assistant with slug '{body.slug}' already exists in this knowledge base."
        ) from exc

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="assistant.create",
        resource_type="assistant",
        resource_id=assistant.id,
    )
    return AssistantRead.model_validate(assistant)


@router.get(
    "",
    response_model=Page[AssistantRead],
    dependencies=[Depends(require_permission("assistant:read"))],
)
async def list_assistants(
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
    pagination: Annotated[PaginationParams, Depends()],
) -> Page[AssistantRead]:
    repo = AssistantRepository(session, tenant_id)
    assistants = await repo.list_for_knowledge_base(
        knowledge_base.id, limit=pagination.limit, offset=pagination.offset
    )
    total = await repo.count_for_knowledge_base(knowledge_base.id)
    return Page(
        items=[AssistantRead.model_validate(a) for a in assistants],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.get(
    "/{assistant_id}",
    response_model=AssistantRead,
    dependencies=[Depends(require_permission("assistant:read"))],
)
async def get_assistant(
    assistant_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> AssistantRead:
    repo = AssistantRepository(session, tenant_id)
    assistant = await repo.get(assistant_id)
    if assistant is None or assistant.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Assistant {assistant_id} not found.")
    return AssistantRead.model_validate(assistant)


@router.delete(
    "/{assistant_id}",
    status_code=204,
    dependencies=[Depends(require_permission("assistant:delete"))],
)
async def delete_assistant(
    assistant_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> None:
    repo = AssistantRepository(session, tenant_id)
    assistant = await repo.get(assistant_id)
    if assistant is None or assistant.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Assistant {assistant_id} not found.")

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="assistant.delete",
        resource_type="assistant",
        resource_id=assistant.id,
    )
    await repo.delete(assistant)
