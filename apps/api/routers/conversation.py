"""Conversation-create/list/update/archive/delete + message-send
endpoints (roadmap steps 178-184), nested four/five levels under
organization (.../assistants/{assistant_id}/conversations[/
{conversation_id}/messages]) -- one/two levels deeper than
routers/assistant.py's own nesting, same "mirror the product
hierarchy" convention every nested router in this codebase already
follows.

Step 184 ("rename/pin/archive/delete") is three endpoints, not four --
rename and pin are folded into ONE `PATCH .../{conversation_id}`
(`ConversationUpdate`, `model_fields_set`-driven partial update), same
"one PATCH, multiple optional fields" shape routers/security_settings.
py:update_security_settings already established, since both are plain
field writes on the SAME resource, not two different actions. `POST
.../{conversation_id}/archive` is its own endpoint, not a third PATCH-
able field, because archiving is a real, VALIDATED state transition
(`conversation_state.py:transition()`, step 181) -- a raw field write
would bypass that validation entirely. Archiving an already-archived
conversation 409s (`InvalidTransitionError` -> `ConflictError`), same
"409 if already in that terminal state" precedent `routers/
invitation.py`'s own revoke endpoint (075) already established, not
silent idempotent success. `DELETE .../{conversation_id}` is a real
hard delete (`ConversationRepository.delete`, cascading to its
`Message` rows via the existing FK), matching every other delete
endpoint in this codebase (Assistant, KnowledgeBase, Workspace) --
`archived` already covers the reversible-ish "soft removal" case, so
delete meaning "actually gone" is the honest, undiluted second option.

New `conversation:update`/`conversation:delete` permissions, same
broad tier as `conversation:create`/`message:create` (every role
except `guest`/`viewer`) -- renaming, pinning, archiving, or deleting
one's OWN conversation is the same core product USE as starting or
continuing one, not admin-tier configuration; `viewer` stays excluded
for the same reason it's excluded from create -- it never owns a
conversation via the real endpoint in the first place.

List (182, "paginated conversation-history endpoint") is scoped to the
CALLER's own conversations only (`ConversationRepository.
list_for_assistant_and_user`), not every conversation in the org --
"conversation HISTORY" reads as personal history, and step 179 already
established a conversation as user-owned, not just tenant-owned (its
own `get_target_conversation` ownership check). A support/admin-wide
"every user's conversations" view would be a genuinely different,
elevated capability this step's literal wording doesn't ask for --
not built here. New `conversation:read` permission, deliberately
broader than `conversation:create`/`message:create`: it includes
`viewer` (reading one's own history is exactly what a read-only role
is for, unlike creating new conversations), still excludes `guest`.

As of step 181, both message-send endpoints transition a `new`
conversation to `active` (via `conversation_state.py:transition()`) the
first time a message is sent into it -- the one real, automatic state
change this codebase can honestly trigger today; see that module's own
docstring and `models/conversation.py`'s for why `waiting`/
`processing`/`completed`/`archived` stay real, legal, but currently
unreached states rather than something faked a trigger for here.

Conversation-create takes no request body -- every field a
Conversation needs (`assistant_id` from the URL, `user_id` from the
caller's own JWT, `tenant_id` from context) is already known without
the client supplying anything; "start a new conversation with this
assistant" is the whole request.

`create` (178) + `list` (182) only -- unlike routers/assistant.py's
full create/list/get/delete: a single-resource `get`/`delete` are
folded into 184's rename/pin/archive/delete work, which still needs
its own design decisions this step has no reason to anticipate.

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

`/messages/stream` (step 180) is a separate endpoint from `/messages`,
not the same route content-negotiated on an `Accept` header or a
`stream: true` body flag -- SSE's response shape (`text/event-stream`,
no `response_model`) is genuinely different from `/messages`'s tested
JSON contract, and FastAPI's `response_model` validation doesn't mix
cleanly with a `StreamingResponse` return. Deliberately honest about
what's actually being streamed: `orchestrator.handle()` still computes
the FULL response before this endpoint ever runs (no roadmap step
through 200 asks for token-level streaming out of the orchestrator/LLM
layer itself) -- what this step delivers is the real, correct SSE
TRANSPORT (a genuinely incremental, chunked HTTP response a browser's
`EventSource`/`fetch` can consume progressively today), word-chunked
for a realistic typing effect, with a real `await asyncio.sleep(0)`
between chunks so Starlette actually flushes each one rather than
coalescing the whole body into a single write. A future token-
streaming generation source can plug into this same transport without
changing the client contract. Both the user's and the assistant's
messages are still persisted in full via the normal ORM/session path
-- streaming only changes how the FINAL response is delivered to this
one caller, not what's stored.

The response's `assistant_message` ORM object is converted to a plain
`MessageRead` (`message_read`) BEFORE the generator closure is built,
never touched from inside `event_stream()` itself -- `get_tenant_db`
commits (and, by SQLAlchemy's `expire_on_commit` default, expires
every attribute on every object tracked by that session) the instant
this endpoint function returns, which happens well before Starlette
ever starts iterating a `StreamingResponse`'s body. Reading ORM
attributes from inside the generator would race that commit against
an already-closed session; capturing an already-validated Pydantic
model by closure sidesteps the issue entirely.

Both message-send endpoints dispatch `message_embedding.py:
dispatch_message_embedding` (`.delay()`) right after EVERY `Message.
create()` -- both the user's turn and the assistant's reply, since
either kind of turn needs to become semantically searchable.

`/search/keyword` and `/search/semantic` (step 183) are two separate
endpoints, not one endpoint with a `mode=` parameter -- same "two
genuinely different mechanisms, not one abstraction" precedent
routers/retrieval.py's own dense/keyword/hybrid split already
established (confirmed there at step 118's own design). Both reuse
`conversation:read`, not a new permission -- searching one's own
conversation history is a read action on that same resource, same
"same capability, different view" reasoning routers/retrieval.py's own
reuse of `knowledge_base:read` already set. `search_semantic`
constructs its own `OpenAIEmbeddingProvider()` singleton
(`_embedding_provider`, module-level, same "each consuming
module gets its own instance" pattern `message_embedding.py`'s own
docstring explains) and computes the QUERY embedding inline,
synchronously -- the same real, live embedding call `routers/
retrieval.py:dense_search` already makes at request time. In an
environment with no real `OPENAI_API_KEY` (documented at steps
107/108/111-114/117/120-122), this fails closed with a plain 500, the
same accepted, honest gap `dense_search` already has; `search_keyword`
has no such dependency and works for real in every environment,
including this one.

As of step 187, `_build_citations` turns `orchestrator.py:
OrchestratorResult.chunks` into real `citations.py:Citation` objects
right after `orchestrator.handle()` returns -- citations.py's own
docstring deliberately keeps it DB-free and expects its caller to
supply a `document_info` lookup, so this router (which already has a
live, request-scoped session) is exactly that caller. Fetches each
unique `Document`/`KnowledgeBase` at most once per request (a `dict`
keyed by `document_id`, not one query per chunk) -- a real response
can cite several chunks from the same document. Stored on the
assistant `Message` as `CitationRead.model_dump(mode="json")` dicts
(see `models/message.py:Message.citations`'s own docstring for why),
never on the user's own message -- nothing retrieves on their behalf,
so `[]` (the column's own default) is already the honest value there,
no need to pass it explicitly.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from citations import Citation, DocumentInfo, build_citations
from context_builder import ContextChunk
from conversation_state import InvalidTransitionError, transition
from dependencies.auth import get_current_user_id
from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from embeddings.openai import OpenAIEmbeddingProvider
from errors import ConflictError, NotFoundError
from message_embedding import dispatch_message_embedding
from models.assistant import Assistant
from models.conversation import Conversation
from orchestrator import OrchestratorResult, orchestrator
from repositories.assistant import AssistantRepository
from repositories.conversation import ConversationRepository
from repositories.document import DocumentRepository
from repositories.knowledge_base import KnowledgeBaseRepository
from repositories.message import MessageRepository
from schemas.common import Page, PaginationParams
from schemas.conversation import ConversationRead, ConversationUpdate
from schemas.message import (
    CitationRead,
    ConversationSearchRequest,
    MessageCreate,
    MessageRead,
    MessageSearchResultRead,
)

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

_embedding_provider = OpenAIEmbeddingProvider()


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


@router.get(
    "",
    response_model=Page[ConversationRead],
    dependencies=[Depends(require_permission("conversation:read"))],
)
async def list_conversations(
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    assistant: TargetAssistant,
    pagination: Annotated[PaginationParams, Depends()],
) -> Page[ConversationRead]:
    repo = ConversationRepository(session, tenant_id)
    conversations = await repo.list_for_assistant_and_user(
        assistant.id, user_id, limit=pagination.limit, offset=pagination.offset
    )
    total = await repo.count_for_assistant_and_user(assistant.id, user_id)
    return Page(
        items=[ConversationRead.model_validate(c) for c in conversations],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


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


@router.patch(
    "/{conversation_id}",
    response_model=ConversationRead,
    dependencies=[Depends(require_permission("conversation:update"))],
)
async def update_conversation(
    body: ConversationUpdate,
    conversation: TargetConversation,
) -> ConversationRead:
    for field_name in body.model_fields_set:
        setattr(conversation, field_name, getattr(body, field_name))
    return ConversationRead.model_validate(conversation)


@router.post(
    "/{conversation_id}/archive",
    response_model=ConversationRead,
    dependencies=[Depends(require_permission("conversation:update"))],
)
async def archive_conversation(conversation: TargetConversation) -> ConversationRead:
    try:
        transition(conversation, "archived")
    except InvalidTransitionError as exc:
        raise ConflictError(str(exc)) from exc
    return ConversationRead.model_validate(conversation)


@router.delete(
    "/{conversation_id}",
    status_code=204,
    dependencies=[Depends(require_permission("conversation:delete"))],
)
async def delete_conversation(
    session: TenantDb,
    tenant_id: TenantId,
    conversation: TargetConversation,
) -> None:
    await ConversationRepository(session, tenant_id).delete(conversation)


def _citation_json(citation: Citation) -> dict[str, object]:
    return CitationRead(
        chunk_id=citation.chunk_id,
        document_id=citation.document_id,
        document_title=citation.document_title,
        knowledge_base_name=citation.knowledge_base_name,
        section=citation.section,
    ).model_dump(mode="json")


async def _build_citations(
    session: AsyncSession, tenant_id: uuid.UUID, result: OrchestratorResult
) -> list[Citation]:
    if not result.chunks:
        return []

    document_repo = DocumentRepository(session, tenant_id)
    knowledge_base_repo = KnowledgeBaseRepository(session, tenant_id)
    document_info: dict[uuid.UUID, DocumentInfo] = {}
    for chunk in result.chunks:
        if chunk.document_id in document_info:
            continue
        document = await document_repo.get(chunk.document_id)
        if document is None:
            continue
        knowledge_base = await knowledge_base_repo.get(document.knowledge_base_id)
        if knowledge_base is None:
            continue
        document_info[chunk.document_id] = DocumentInfo(
            title=document.title, knowledge_base_name=knowledge_base.name
        )

    context_chunks = [
        ContextChunk(id=chunk.chunk_id, document_id=chunk.document_id, text=chunk.text)
        for chunk in result.chunks
        if chunk.document_id in document_info
    ]
    return build_citations(context_chunks, document_info=document_info)


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
    if conversation.status == "new":
        transition(conversation, "active")

    repo = MessageRepository(session, tenant_id)
    user_message = await repo.create(
        conversation_id=conversation.id,
        role="user",
        content=body.content,
    )
    dispatch_message_embedding.delay(str(user_message.id), str(tenant_id))

    result = await orchestrator.handle(
        body.content, tenant_id=tenant_id, knowledge_base_id=assistant.knowledge_base_id
    )
    citations = await _build_citations(session, tenant_id, result)

    assistant_message = await repo.create(
        conversation_id=conversation.id,
        role="assistant",
        content=result.response,
        citations=[_citation_json(c) for c in citations],
    )
    dispatch_message_embedding.delay(str(assistant_message.id), str(tenant_id))

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="message.create",
        resource_type="message",
        resource_id=assistant_message.id,
    )
    return MessageRead.model_validate(assistant_message)


@router.post(
    "/{conversation_id}/messages/stream",
    dependencies=[Depends(require_permission("message:create"))],
)
async def send_message_streaming(
    body: MessageCreate,
    session: TenantDb,
    tenant_id: TenantId,
    assistant: TargetAssistant,
    conversation: TargetConversation,
) -> StreamingResponse:
    if conversation.status == "new":
        transition(conversation, "active")

    repo = MessageRepository(session, tenant_id)
    user_message = await repo.create(
        conversation_id=conversation.id,
        role="user",
        content=body.content,
    )
    dispatch_message_embedding.delay(str(user_message.id), str(tenant_id))

    result = await orchestrator.handle(
        body.content, tenant_id=tenant_id, knowledge_base_id=assistant.knowledge_base_id
    )
    citations = await _build_citations(session, tenant_id, result)

    assistant_message = await repo.create(
        conversation_id=conversation.id,
        role="assistant",
        content=result.response,
        citations=[_citation_json(c) for c in citations],
    )
    dispatch_message_embedding.delay(str(assistant_message.id), str(tenant_id))

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="message.create",
        resource_type="message",
        resource_id=assistant_message.id,
    )
    # Captured by the generator below via closure -- see this module's
    # own docstring for why the ORM object itself must not be touched
    # from inside event_stream().
    message_read = MessageRead.model_validate(assistant_message)

    async def event_stream() -> AsyncIterator[str]:
        words = result.response.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else f"{word} "
            yield f"event: message\ndata: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0)
        yield f"event: done\ndata: {message_read.model_dump_json()}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post(
    "/search/keyword",
    response_model=list[MessageSearchResultRead],
    dependencies=[Depends(require_permission("conversation:read"))],
)
async def search_conversations_keyword(
    body: ConversationSearchRequest,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    assistant: TargetAssistant,
) -> list[MessageSearchResultRead]:
    repo = MessageRepository(session, tenant_id)
    results = await repo.search_keyword(assistant.id, user_id, body.query, top_k=body.top_k)
    return [
        MessageSearchResultRead(
            message_id=r.message_id,
            conversation_id=r.conversation_id,
            content=r.content,
            score=r.score,
        )
        for r in results
    ]


@router.post(
    "/search/semantic",
    response_model=list[MessageSearchResultRead],
    dependencies=[Depends(require_permission("conversation:read"))],
)
async def search_conversations_semantic(
    body: ConversationSearchRequest,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    assistant: TargetAssistant,
) -> list[MessageSearchResultRead]:
    vectors = await _embedding_provider.embed([body.query])
    repo = MessageRepository(session, tenant_id)
    results = await repo.search_semantic(assistant.id, user_id, vectors[0], top_k=body.top_k)
    return [
        MessageSearchResultRead(
            message_id=r.message_id,
            conversation_id=r.conversation_id,
            content=r.content,
            score=r.score,
        )
        for r in results
    ]
