"""Conversation-create endpoint (roadmap step 178), nested four levels
under organization (.../assistants/{assistant_id}/conversations) --
one level deeper than routers/assistant.py's own nesting, same
"mirror the product hierarchy" convention every nested router in this
codebase already follows.

Only `create` -- step 178's own literal wording, unlike routers/
assistant.py's full create/list/get/delete: list is step 182's own
"paginated conversation-history endpoint", get/delete are folded into
184's rename/pin/archive/delete work. Building those now would be
speculating about shapes (pagination filters, a status field that
doesn't exist until 181) those later steps still need to decide.

Takes no request body -- every field a Conversation needs
(`assistant_id` from the URL, `user_id` from the caller's own JWT,
`tenant_id` from context) is already known without the client
supplying anything; "start a new conversation with this assistant" is
the whole request.

The assistant-resolution dependency is inline here, not promoted to
dependencies/assistant.py -- same "build inline for the first
consumer, promote once a second real consumer needs it" discipline
dependencies/knowledge_base.py's own docstring (step 120) already
established. This is that first consumer.

`conversation:create` is granted to every role except `guest`
("gets nothing yet", matching every other permission's precedent) and
`viewer` (explicitly read-only in spirit — it has never appeared in a
GRANTED_ROLES create list anywhere else in this codebase). Unlike
`assistant:create`/`knowledge_base:create` (org_owner/admin/manager
only -- configuring the product), starting a conversation is core
product USE, not configuration, so it belongs to every role that
isn't purely read-only or explicitly permissionless.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from dependencies.auth import get_current_user_id
from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import NotFoundError
from models.assistant import Assistant
from repositories.assistant import AssistantRepository
from repositories.conversation import ConversationRepository
from schemas.conversation import ConversationRead

router = APIRouter(
    prefix=(
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}/assistants/{assistant_id}/conversations"
    ),
    tags=["conversations"],
)

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]
UserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


async def get_target_assistant(
    assistant_id: uuid.UUID,
    knowledge_base: TargetKnowledgeBase,
    session: TenantDb,
    tenant_id: TenantId,
) -> Assistant:
    assistant = await AssistantRepository(session, tenant_id).get(assistant_id)
    if assistant is None or assistant.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Assistant {assistant_id} not found.")
    return assistant


TargetAssistant = Annotated[Assistant, Depends(get_target_assistant)]


@router.post(
    "",
    response_model=ConversationRead,
    status_code=201,
    dependencies=[Depends(require_permission("conversation:create"))],
)
async def create_conversation(
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    assistant: TargetAssistant,
) -> ConversationRead:
    repo = ConversationRepository(session, tenant_id)
    conversation = await repo.create(assistant_id=assistant.id, user_id=user_id)

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="conversation.create",
        resource_type="conversation",
        resource_id=conversation.id,
    )
    return ConversationRead.model_validate(conversation)
