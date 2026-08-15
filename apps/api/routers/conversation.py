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
for a realistic typing effect. A future token-streaming generation
source can plug into this same transport without changing the client
contract. Both the user's and the assistant's messages are still
persisted in full via the normal ORM/session path -- streaming only
changes how the FINAL response is delivered to this one caller, not
what's stored.

As of step 194, this endpoint calls `generate_assistant_reply` for
persistence (the same helper `send_message` already used) and
`message_processing.py:build_message_stream` for the SSE formatting,
rather than inlining both -- `routers/public_conversation.py`'s own new
anonymous streaming endpoint (built the same step, for the real chat UI
shell in `apps/web`, which has no auth UI yet to reach this
authenticated router) needed the identical word-chunked SSE shape, one
real second caller being exactly the bar this codebase already applies
before sharing logic. The response's `assistant_message` ORM object is
still converted to a plain `MessageRead` BEFORE the generator is built,
never touched from inside it -- `get_tenant_db` commits (and, by
SQLAlchemy's `expire_on_commit` default, expires every attribute on
every object tracked by that session) the instant this endpoint
function returns, well before Starlette ever starts iterating a
`StreamingResponse`'s body; `build_message_stream` only ever reads from
the already-validated `MessageRead`, never the ORM object, preserving
that same safety property.

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

As of step 187, `message_processing.py:build_citations_for_result`
turns `orchestrator.py:OrchestratorResult.chunks` into real
`citations.py:Citation` objects right after `orchestrator.handle()`
returns -- citations.py's own docstring deliberately keeps it DB-free
and expects its caller to supply a `document_info` lookup; `message_
processing.py` is that caller. Fetches each unique `Document`/
`KnowledgeBase` at most once per request (a `dict` keyed by
`document_id`, not one query per chunk) -- a real response can cite
several chunks from the same document. Stored on the assistant
`Message` as `CitationRead.model_dump(mode="json")` dicts (see
`models/message.py:Message.citations`'s own docstring for why), never
on the user's own message -- nothing retrieves on their behalf, so
`[]` (the column's own default) is already the honest value there, no
need to pass it explicitly. As of step 192, this logic (plus `message_
processing.py:generate_assistant_reply`, the "process one turn" core
`send_message` itself now just calls) moved out of this router
entirely, once `routers/public_conversation.py`'s own anonymous
message-send became a second real caller -- see that module's own
docstring for why a router shouldn't import from another router.

`POST .../{conversation_id}/messages/{message_id}/regenerate` (step
188) UPDATES the existing assistant `Message` row in place rather than
creating a new one or building message versioning/branching -- no
roadmap step through 200 asks for parallel response versions, and this
codebase's `Message` model has no parent/sibling/version link to
support one; "regenerate THE response" (singular) reads as replacing
it, the simplest honest interpretation. `get_target_message` (another
inline, first-consumer dependency) resolves the message and requires
`role == "assistant"` -- regenerating a user's own turn is
nonsensical. `MessageRepository.get_preceding_user_message` finds the
real query that produced this reply by nearest-earlier-`created_at`
in the same conversation, not a stored reply-to link -- messages
strictly alternate user/assistant in this codebase's own real flow (a
guarantee `send_message`/`send_message_streaming` both maintain), so
that's unambiguous without one. Re-dispatches embedding for the
updated content -- the old embedding is now stale, describing text
that no longer exists at that message id. Reuses `message:create`,
not a new permission -- regenerating is the same capability tier as
originally producing that reply, not a distinct action.

`PUT`/`DELETE .../{conversation_id}/messages/{message_id}/feedback`
(step 189) set/clear `Message.feedback_type`, reusing `get_target_
message` (so feedback can only ever target a real assistant reply,
same reasoning `regenerate` already established). Two endpoints, not
one PATCH accepting `feedback_type: FeedbackType | None` -- setting a
value and clearing it are different intents (rate this reply vs.
retract that rating) worth distinct, self-documenting verbs, matching
this codebase's own `PUT`-for-"set the current value of a single-value
sub-resource" convention rather than `ConversationUpdate`'s multi-
field `model_fields_set` partial-update shape, which exists
specifically for resources with MULTIPLE independent optional fields
-- feedback has exactly one.

`POST .../{conversation_id}/messages/{message_id}/follow-up-questions`
(step 190) calls `follow_up_questions.py:generate_follow_up_questions`
-- a real LLM call, see that module's own docstring for why it's a
separate endpoint rather than something computed inline during
message-send (keeping that endpoint's own "works in every environment"
property intact) and why nothing is persisted. Reuses `get_target_
message`/`get_preceding_user_message`, the same "find the real query
this reply answers" building block `regenerate` already established.

`GET .../{conversation_id}/export` (step 191) is ONE endpoint with a
`format` query param (`"json"`/`"markdown"`), not a URL-path split
like `/search/keyword` vs `/search/semantic` -- that split exists for
genuinely different retrieval MECHANISMS; export is one data fetch
(the full, ordered transcript, `MessageRepository.list_for_conversation`,
new this step -- nothing needed the whole conversation back in order
until now) with two SERIALIZATION choices over the identical data,
much closer to `ContextSearchRequest.strategy`'s own "one endpoint,
a field picks the shape" precedent than to the mechanism split.
`ConversationExportRead` (JSON) and `_render_conversation_markdown`
both build from `ConversationRead`/`MessageRead`/the same message list
-- no separate query for each format. Both responses carry a real
`Content-Disposition: attachment` header -- AGENTS.md's own "Download
conversations" phrasing (not just "view/read them"), so this behaves
like an actual file download, not just a differently-shaped read.
Reuses `conversation:read` -- exporting one's own conversation is a
read action, same "same capability, different view" reasoning already
established elsewhere in this router.

`POST .../conversations/claim` (step 193, AGENTS.md's own "USER
IDENTIFICATION" section: "when a user provides identifying
information... the system should intelligently reconnect them with
their previous history... relevant memories") is this router's own
side of the anonymous-to-identified handoff step 192's public router
made possible. Deliberately takes NO `conversation_id` path/body
field beyond the anonymous token itself -- `auth/jwt.py:decode_
anonymous_session_token` already names exactly one conversation, and a
second, independently-supplied id would only exist to be checked
against the token's own for agreement, the same redundancy `routers/
public_conversation.py:get_anonymous_conversation` already declined to
introduce. Requires a REAL authenticated caller (this router's normal
JWT + RBAC + tenant context, unlike the public router) -- proving
"who I am now" is the whole point of a claim, so this is deliberately
NOT reachable from the unauthenticated public router at all. Rejects
(404, not 200-with-no-op) a conversation that doesn't belong to THIS
assistant or that already has a `user_id` -- an already-claimed or
foreign conversation is not this caller's to reconnect with, same
"mismatch 404s" precedent `get_target_conversation` itself already
established. Reuses `conversation:update`, not a new permission --
changing who owns a conversation is the same tier as renaming/pinning
it, not a distinct capability. Does NOT touch `conversation.status` --
claiming is purely an ownership change, not a lifecycle transition
`conversation_state.py`'s own `VALID_TRANSITIONS` has any real state
for. Calls `memory_retrieval.py:retrieve_memory_for_conversation_start`
(166, unwired until this step -- its own docstring says as much) with
the now-real `tenant_id`/`user_id` and returns the result directly in
the response rather than threading it into `orchestrator.handle()`:
no chat UI exists yet to consume a prompt-injected version, and
AGENTS.md's own example list ("Relevant memories," "Saved context")
reads as things a CLIENT surfaces to the user, not necessarily
something silently fed into generation -- widening `handle()`'s
signature again, so soon after step 187's own deliberate widening,
would be speculating ahead of a step that actually needs it.
Deliberately stays scoped to MEMORY reconnection only (this step's own
literal name), not conversation-HISTORY reconnection (AGENTS.md's
"Previous conversations" example) -- `list_conversations` (182)
already provides that separately once a conversation is claimed and
reachable through the normal authenticated list, so returning it again
here would just be duplicating an existing capability, not adding one.

`rate_limit_message_send` (step 199, AGENTS.md's own "RATE LIMITING"
section: "Conversation requests"/"Tenant-specific limits") gates
`send_message`/`send_message_streaming`/`regenerate_response` -- every
real caller of `orchestrator.handle()` in this router, the actual cost
being protected. Keyed by `tenant_id`, not by caller or conversation,
and shares its Redis key prefix with `routers/public_conversation.py`'s
own anonymous equivalent (`rate_limit.py`'s own docstring explains why
one shared per-tenant budget, not two). Built on `rate_limit.py:
check_rate_limit`, the same real fixed-window Redis logic
`rate_limit()`'s per-IP auth-route dependency already used -- this
router just resolves its own KEY (tenant_id, from the already-real
`get_current_tenant_id`) rather than a client IP.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from auth.jwt import TokenError, decode_anonymous_session_token
from conversation_state import InvalidTransitionError, transition
from dependencies.auth import get_current_user_id
from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from embeddings.openai import OpenAIEmbeddingProvider
from errors import ConflictError, NotFoundError, UnauthorizedError
from follow_up_questions import generate_follow_up_questions
from memory_retrieval import retrieve_memory_for_conversation_start
from message_embedding import dispatch_message_embedding
from message_processing import (
    build_citations_for_result,
    build_message_stream,
    citation_json,
    generate_assistant_reply,
)
from models.assistant import Assistant
from models.conversation import Conversation
from models.message import Message
from orchestrator import orchestrator
from rate_limit import MESSAGE_SEND_RATE_LIMIT, check_rate_limit
from repositories.assistant import AssistantRepository
from repositories.conversation import ConversationRepository
from repositories.message import MessageRepository
from schemas.common import Page, PaginationParams
from schemas.conversation import (
    ConversationClaimRead,
    ConversationClaimRequest,
    ConversationExportRead,
    ConversationRead,
    ConversationUpdate,
)
from schemas.memory import MemoryRead
from schemas.message import (
    ConversationSearchRequest,
    FollowUpQuestionsRead,
    MessageCreate,
    MessageFeedbackCreate,
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


async def rate_limit_message_send(tenant_id: TenantId) -> None:
    await check_rate_limit(
        f"message_send:{tenant_id}", limit=MESSAGE_SEND_RATE_LIMIT, window_seconds=60
    )


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


@router.post(
    "/claim",
    response_model=ConversationClaimRead,
    dependencies=[Depends(require_permission("conversation:update"))],
)
async def claim_conversation(
    body: ConversationClaimRequest,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    assistant: TargetAssistant,
) -> ConversationClaimRead:
    try:
        conversation_id = decode_anonymous_session_token(body.anonymous_token)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired anonymous session.") from exc

    repo = ConversationRepository(session, tenant_id)
    conversation = await repo.get(conversation_id)
    if (
        conversation is None
        or conversation.assistant_id != assistant.id
        or conversation.user_id is not None
    ):
        raise NotFoundError(f"Conversation {conversation_id} not found.")

    # flush()+refresh() is load-bearing here, same root cause step 189's
    # own diagnostic already confirmed for Message.feedback_type: this
    # row's `updated_at` (onupdate=func.now(), server-computed) is left
    # expired once ANY flush executes this UPDATE -- unlike update_
    # conversation/archive_conversation (which return straight through
    # to model_validate() with no other query in between, so autoflush
    # never fires before validation), retrieve_memory_for_conversation_
    # start's own SELECT queries below trigger exactly that autoflush.
    # Without refresh(), ConversationRead.model_validate() raises a real
    # MissingGreenlet trying to lazily reload an expired attribute from
    # Pydantic's own synchronous validation code.
    conversation.user_id = user_id
    await session.flush()
    await session.refresh(conversation)

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="conversation.claim",
        resource_type="conversation",
        resource_id=conversation.id,
    )

    memories = await retrieve_memory_for_conversation_start(session, tenant_id, user_id)
    return ConversationClaimRead(
        conversation=ConversationRead.model_validate(conversation),
        memories=[MemoryRead.model_validate(m) for m in memories],
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


def _render_conversation_markdown(
    assistant: Assistant, conversation: Conversation, messages: Sequence[Message]
) -> str:
    title = conversation.title or f"Conversation with {assistant.name}"
    lines = [
        f"# {title}",
        "",
        f"**Status:** {conversation.status}  ",
        f"**Started:** {conversation.created_at.isoformat()}",
        "",
    ]
    for message in messages:
        heading = "User" if message.role == "user" else "Assistant"
        lines.append(f"## {heading} — {message.created_at.isoformat()}")
        lines.append("")
        lines.append(message.content)
        lines.append("")
    return "\n".join(lines)


@router.get(
    "/{conversation_id}/export",
    dependencies=[Depends(require_permission("conversation:read"))],
)
async def export_conversation(
    session: TenantDb,
    tenant_id: TenantId,
    assistant: TargetAssistant,
    conversation: TargetConversation,
    format: Literal["json", "markdown"] = "json",
) -> Response:
    messages = await MessageRepository(session, tenant_id).list_for_conversation(conversation.id)

    if format == "markdown":
        content = _render_conversation_markdown(assistant, conversation, messages)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="conversation.md"'},
        )

    export = ConversationExportRead(
        conversation=ConversationRead.model_validate(conversation),
        messages=[MessageRead.model_validate(m) for m in messages],
    )
    return Response(
        content=export.model_dump_json(),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="conversation.json"'},
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=201,
    dependencies=[
        Depends(require_permission("message:create")),
        Depends(rate_limit_message_send),
    ],
)
async def send_message(
    body: MessageCreate,
    session: TenantDb,
    tenant_id: TenantId,
    assistant: TargetAssistant,
    conversation: TargetConversation,
) -> MessageRead:
    assistant_message = await generate_assistant_reply(
        session, tenant_id, assistant, conversation, body.content
    )

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
    dependencies=[
        Depends(require_permission("message:create")),
        Depends(rate_limit_message_send),
    ],
)
async def send_message_streaming(
    body: MessageCreate,
    session: TenantDb,
    tenant_id: TenantId,
    assistant: TargetAssistant,
    conversation: TargetConversation,
) -> StreamingResponse:
    assistant_message = await generate_assistant_reply(
        session, tenant_id, assistant, conversation, body.content
    )

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="message.create",
        resource_type="message",
        resource_id=assistant_message.id,
    )
    # Captured by build_message_stream via closure -- see this module's
    # own docstring for why the ORM object itself must not be touched
    # from inside that generator.
    message_read = MessageRead.model_validate(assistant_message)

    return StreamingResponse(build_message_stream(message_read), media_type="text/event-stream")


async def get_target_message(
    message_id: uuid.UUID,
    conversation: TargetConversation,
    session: TenantDb,
    tenant_id: TenantId,
) -> Message:
    message = await MessageRepository(session, tenant_id).get(message_id)
    if message is None or message.conversation_id != conversation.id or message.role != "assistant":
        raise NotFoundError(f"Message {message_id} not found.")
    return message


TargetMessage = Annotated[Message, Depends(get_target_message)]


@router.post(
    "/{conversation_id}/messages/{message_id}/regenerate",
    response_model=MessageRead,
    dependencies=[
        Depends(require_permission("message:create")),
        Depends(rate_limit_message_send),
    ],
)
async def regenerate_response(
    session: TenantDb,
    tenant_id: TenantId,
    assistant: TargetAssistant,
    conversation: TargetConversation,
    message: TargetMessage,
) -> MessageRead:
    repo = MessageRepository(session, tenant_id)
    user_message = await repo.get_preceding_user_message(conversation.id, before=message.created_at)
    if user_message is None:
        raise NotFoundError(f"No preceding user message found for message {message.id}.")

    result = await orchestrator.handle(
        user_message.content, tenant_id=tenant_id, knowledge_base_id=assistant.knowledge_base_id
    )
    citations = await build_citations_for_result(session, tenant_id, result)

    message.content = result.response
    message.citations = [citation_json(c) for c in citations]
    dispatch_message_embedding.delay(str(message.id), str(tenant_id))

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="message.regenerate",
        resource_type="message",
        resource_id=message.id,
    )
    return MessageRead.model_validate(message)


@router.put(
    "/{conversation_id}/messages/{message_id}/feedback",
    response_model=MessageRead,
    dependencies=[Depends(require_permission("message:create"))],
)
async def set_message_feedback(
    body: MessageFeedbackCreate,
    session: TenantDb,
    tenant_id: TenantId,
    message: TargetMessage,
) -> MessageRead:
    # The explicit flush()+refresh() pair is load-bearing, confirmed
    # live by adding a real diagnostic print and comparing against
    # regenerate_response's own working case: updating feedback_type
    # ALONE (nothing else on this row) leaves updated_at/search_vector
    # genuinely expired after flush -- regenerate_response's own
    # content update doesn't hit this because changing content is what
    # search_vector's GENERATED expression actually depends on, so
    # Postgres's RETURNING clause refreshes both columns for free
    # there. Without refresh(), MessageRead.model_validate() below
    # raises a real MissingGreenlet trying to lazily reload an expired
    # attribute from Pydantic's own synchronous validation code.
    message.feedback_type = body.feedback_type
    await session.flush()
    await session.refresh(message)

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="message.feedback",
        resource_type="message",
        resource_id=message.id,
    )
    return MessageRead.model_validate(message)


@router.delete(
    "/{conversation_id}/messages/{message_id}/feedback",
    status_code=204,
    dependencies=[Depends(require_permission("message:create"))],
)
async def clear_message_feedback(
    session: TenantDb,
    tenant_id: TenantId,
    message: TargetMessage,
) -> None:
    message.feedback_type = None

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="message.feedback_clear",
        resource_type="message",
        resource_id=message.id,
    )


@router.post(
    "/{conversation_id}/messages/{message_id}/follow-up-questions",
    response_model=FollowUpQuestionsRead,
    dependencies=[Depends(require_permission("message:create"))],
)
async def generate_message_follow_up_questions(
    session: TenantDb,
    tenant_id: TenantId,
    conversation: TargetConversation,
    message: TargetMessage,
) -> FollowUpQuestionsRead:
    repo = MessageRepository(session, tenant_id)
    user_message = await repo.get_preceding_user_message(conversation.id, before=message.created_at)
    if user_message is None:
        raise NotFoundError(f"No preceding user message found for message {message.id}.")

    questions = await generate_follow_up_questions(user_message.content, message.content)
    return FollowUpQuestionsRead(questions=questions)


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
