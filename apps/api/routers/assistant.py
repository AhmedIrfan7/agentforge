"""Assistant CRUD (roadmap step 160), nested three levels under
organization
(/organizations/{id}/workspaces/{id}/knowledge-bases/{id}/assistants)
matching the product hierarchy (AGENTS.md's "ORGANIZATION STRUCTURE":
org -> workspace -> knowledge base -> AI assistant -> ...), one level
deeper than routers/knowledge_base.py's own nesting.

As of step 238 (the assistant-builder UI), a real PATCH endpoint
exists too (assistant:update, migration 331109d18ff0) -- the design
decision this docstring used to defer (partial vs. full replacement of
agent_configuration) landed as a whole-object REPLACE on that one
field when included, same model_fields_set-driven PATCH shape every
other update endpoint in this codebase already uses; see
schemas/assistant.py:AssistantUpdate's own docstring for why a deep
merge would be wrong here.

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
from dependencies.auth import get_current_user_id
from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import ConflictError, NotFoundError
from repositories.assistant import AssistantRepository
from schemas.assistant import AssistantCreate, AssistantRead, AssistantUpdate
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
UserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


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
    user_id: UserId,
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
        actor_user_id=user_id,
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


@router.patch(
    "/{assistant_id}",
    response_model=AssistantRead,
    dependencies=[Depends(require_permission("assistant:update"))],
)
async def update_assistant(
    assistant_id: uuid.UUID,
    body: AssistantUpdate,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    knowledge_base: TargetKnowledgeBase,
) -> AssistantRead:
    repo = AssistantRepository(session, tenant_id)
    assistant = await repo.get(assistant_id)
    if assistant is None or assistant.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Assistant {assistant_id} not found.")

    # Only fields the caller actually included get applied --
    # model_fields_set-driven PATCH semantics, same pattern every other
    # update endpoint in this codebase already uses. agent_configuration
    # needs .model_dump() before it can go into the JSONB column, same
    # reasoning create_assistant's own body.agent_configuration.
    # model_dump() call above already established -- setattr() alone
    # would store a live Pydantic object where the column expects a
    # plain dict.
    for field_name in body.model_fields_set:
        value = getattr(body, field_name)
        if field_name == "agent_configuration" and value is not None:
            value = value.model_dump()
        setattr(assistant, field_name, value)

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="assistant.update",
        resource_type="assistant",
        resource_id=assistant.id,
        actor_user_id=user_id,
    )
    # write_audit_log's own internal flush() expires updated_at
    # (onupdate=func.now(), server-computed) -- a real, awaited refresh
    # gets the actual persisted value back instead of Pydantic's
    # synchronous model_validate raising MissingGreenlet trying to
    # lazy-load it, same fix routers/organization.py's own PATCH
    # endpoint needed at step 234.
    await session.refresh(assistant)
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
    user_id: UserId,
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
        actor_user_id=user_id,
    )
    await repo.delete(assistant)
