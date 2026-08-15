"""Conversation-create + message-send endpoints (roadmap steps 178-179),
nested four/five levels under organization (.../assistants/
{assistant_id}/conversations[/{conversation_id}/messages]) -- one/two
levels deeper than routers/assistant.py's own nesting, same "mirror
the product hierarchy" convention every nested router in this codebase
already follows.

Conversation-create takes no request body -- every field a
Conversation needs (`assistant_id` from the URL, `user_id` from the
caller's own JWT, `tenant_id` from context) is already known without
the client supplying anything; "start a new conversation with this
assistant" is the whole request.

Only conversation `create` (178) -- unlike routers/assistant.py's full
create/list/get/delete: list is step 182's own "paginated conversation-
history endpoint", get/delete are folded into 184's rename/pin/archive/
delete work. Building those now would be speculating about shapes
(pagination filters, a status field that doesn't exist until 181)
those later steps still need to decide.

Message-send (179) is genuinely just "wired through orchestrator" --
`orchestrator.py:orchestrator.handle(query, tenant_id=..., knowledge_base_id=...)`
already exists as a real, tested entry point since step 143 (its own
docstring explicitly named "a future chat/conversation endpoint" as
the caller it was built for); this endpoint is that caller, not a
redesign of it. Deliberately does NOT thread prior message history
into `handle()` -- that signature is real and honest today (single
query in, single response out), and history-aware generation isn't
what step 179's own literal wording asks for; extending it would be
speculating ahead of a step that actually needs it, the same
discipline `llm/base.py`'s own "add a method when the step that needs
it lands" precedent already established. Persists the caller's message
AND the orchestrator's response as two real `Message` rows (role
"user"/"assistant") via the endpoint's own request-scoped session --
`orchestrator.handle()` stays fully decoupled from that session,
managing its own internal DB access for retrieval exactly as it did
before this endpoint existed.

Both resolution dependencies (`get_target_assistant`, `get_target_
conversation`) are inline here, not promoted to a shared dependencies/
module -- same "build inline for the first consumer, promote once a
second real consumer needs it" discipline dependencies/
knowledge_base.py's own docstring (step 120) already established.
`get_target_conversation` additionally checks the conversation's own
`user_id` against the caller -- a conversation is user-owned, not just
tenant-owned (unlike Assistant/KnowledgeBase), so RBAC tier alone
isn't enough: a role permission answers "can this role use
conversations at all", ownership answers "is this THEIR conversation"
-- re-checked live on every request, not just at creation time, same
"no implicit inheritance" lesson this codebase's RLS/RBAC bugs (steps
072, 074, 090) already taught. A mismatch 404s, not 403s, matching
every other cross-resource mismatch in this codebase (Assistant vs.
KnowledgeBase, KnowledgeBase vs. Workspace) -- existence of another
user's conversation is not information this endpoint should confirm.

`conversation:create`/`message:create` are both granted to every role
except `guest` ("gets nothing yet", matching every other permission's
precedent) and `viewer` (explicitly read-only in spirit — it has never
appeared in a GRANTED_ROLES create list anywhere else in this
codebase). Unlike `assistant:create`/`knowledge_base:create`
(org_owner/admin/manager only -- configuring the product), starting or
continuing a conversation is core product USE, not configuration, so
it belongs to every role that isn't purely read-only or explicitly
permissionless.
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
from models.conversation import Conversation
from orchestrator import orchestrator
from repositories.assistant import AssistantRepository
from repositories.conversation import ConversationRepository
from repositories.message import MessageRepository
from schemas.conversation import ConversationRead
from schemas.message import MessageCreate, MessageRead

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


async def get_target_conversation(
    conversation_id: uuid.UUID,
    assistant: TargetAssistant,
    user_id: UserId,
    session: TenantDb,
    tenant_id: TenantId,
) -> Conversation:
    conversation = await ConversationRepository(session, tenant_id).get(conversation_id)
    if (
        conversation is None
        or conversation.assistant_id != assistant.id
        or conversation.user_id != user_id
    ):
        raise NotFoundError(f"Conversation {conversation_id} not found.")
    return conversation


TargetConversation = Annotated[Conversation, Depends(get_target_conversation)]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=201,
    dependencies=[Depends(require_permission("message:create"))],
)
async def send_message(
    body: MessageCreate,
    session: TenantDb,
    tenant_id: TenantId,
    assistant: TargetAssistant,
    conversation: TargetConversation,
) -> MessageRead:
    repo = MessageRepository(session, tenant_id)
    await repo.create(
        conversation_id=conversation.id,
        role="user",
        content=body.content,
    )

    response_text = await orchestrator.handle(
        body.content, tenant_id=tenant_id, knowledge_base_id=assistant.knowledge_base_id
    )

    assistant_message = await repo.create(
        conversation_id=conversation.id,
        role="assistant",
        content=response_text,
    )

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="message.create",
        resource_type="message",
        resource_id=assistant_message.id,
    )
    return MessageRead.model_validate(assistant_message)
