"""Anonymous-session conversation endpoints (roadmap step 192,
Milestone 6) -- "pre-auth visitors": the embeddable-widget deployment
channel AGENTS.md's own "DEPLOYMENT CHANNELS" section names (Milestone
7, not yet built) needs a real visitor who has never signed up, not
just an already-authenticated user. `models/conversation.py:
Conversation.user_id` has been nullable since step 176 specifically
for this, unexercised until now.

A genuinely separate router from `routers/conversation.py`, not a
content-negotiated branch of it -- everything under `/organizations/
{organization_id}/...` requires `dependencies/tenant.py:
get_current_tenant_id` (a real JWT + a real Membership row), which an
anonymous visitor fundamentally can't satisfy. This router is instead
keyed by `assistant_id` alone (`/public/assistants/{assistant_id}/...`),
the one identifier a real embeddable widget script tag can carry
(`<script data-assistant-id="...">`, the standard shape this class of
product already uses elsewhere) -- no organization/workspace/
knowledge-base path segments a visitor could never resolve.

Public reachability is OPT-IN per assistant (`models/assistant.py:
Assistant.is_public`, default `False`) -- knowing an Assistant's
(non-guessable, but not secret) UUID must not be sufficient on its own
to reach it anonymously; `repositories/assistant.py:
get_public_assistant_by_id` checks `is_public=True` in the application
layer on top of a new, narrowly-scoped permissive RLS policy
(`assistant_by_id`, migration `4effc7a3a36e`) that only makes the row
visible enough to check that flag before any tenant context exists --
same "second permissive policy keyed on a session variable, not a
blanket bypass" shape `invitation_by_token` already established for
accepting an Invitation by raw token (step 074).

Ownership of an anonymous Conversation (`user_id IS NULL`) is proven
by a real, signed JWT (`auth/jwt.py:create_anonymous_session_token`/
`decode_anonymous_session_token`, `type "anonymous_session"` --
rejected by `decode_access_token` outright, same `mfa_pending`-ticket
precedent) scoped to exactly the one conversation_id it was issued
for, returned once at creation time and required as a Bearer
credential on every message sent into that conversation afterward --
there is no username/password/account behind it, only "you are
whoever started this specific conversation." A mismatched, missing, or
foreign-conversation token 401s; a real conversation that isn't
anonymous, or doesn't belong to this assistant, 404s -- same "don't
leak existence" precedent every other cross-resource mismatch in this
codebase already uses.

`generate_assistant_reply` (`message_processing.py`, promoted out of
routers/conversation.py this same step) does the real message-send
work -- citations, embedding dispatch, orchestrator call, state
transition -- identically to the authenticated flow; only the
resolution/authorization layer above it differs. No RBAC permission
check anywhere in this router -- there is no Membership/role for an
anonymous caller to hold one; the anonymous session token itself is
the entire authorization model.

`POST .../{conversation_id}/messages/stream` (step 194) is this
router's own anonymous counterpart to `routers/conversation.py:
send_message_streaming` (180) -- added specifically so the real chat UI
shell step 194 builds in `apps/web` has a genuine SSE transport to
render against: no dashboard auth UI exists yet (`docs/ROADMAP.md`
step 233, "auth-gated layout," is well after this one), so the public,
zero-auth anonymous flow is the only backend surface a real frontend
page can honestly stream from today, the same reasoning that made this
whole router's anonymous session model worth building at 192. Built on
the same `message_processing.py:generate_assistant_reply`/`build_
message_stream` pair the authenticated endpoint now uses (see that
module's own docstring) -- not a second, duplicated inline
implementation.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from auth.jwt import TokenError, create_anonymous_session_token, decode_anonymous_session_token
from db import set_tenant_context
from dependencies.db import get_db
from errors import NotFoundError, UnauthorizedError
from message_processing import build_message_stream, generate_assistant_reply
from models.assistant import Assistant
from models.conversation import Conversation
from repositories.assistant import get_public_assistant_by_id
from repositories.conversation import ConversationRepository
from schemas.conversation import AnonymousConversationRead
from schemas.message import MessageCreate, MessageRead

router = APIRouter(prefix="/public/assistants/{assistant_id}/conversations", tags=["public-chat"])

PublicDb = Annotated[AsyncSession, Depends(get_db)]

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_public_assistant(assistant_id: uuid.UUID, session: PublicDb) -> Assistant:
    assistant = await get_public_assistant_by_id(session, assistant_id)
    if assistant is None:
        raise NotFoundError(f"Assistant {assistant_id} not found.")
    await set_tenant_context(session, assistant.tenant_id)
    return assistant


PublicAssistant = Annotated[Assistant, Depends(get_public_assistant)]


async def get_anonymous_conversation(
    conversation_id: uuid.UUID,
    assistant: PublicAssistant,
    session: PublicDb,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> Conversation:
    if credentials is None:
        raise UnauthorizedError("Missing or invalid anonymous session token.")
    try:
        token_conversation_id = decode_anonymous_session_token(credentials.credentials)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired session.") from exc
    if token_conversation_id != conversation_id:
        raise UnauthorizedError("Invalid or expired session.")

    conversation = await ConversationRepository(session, assistant.tenant_id).get(conversation_id)
    if (
        conversation is None
        or conversation.assistant_id != assistant.id
        or conversation.user_id is not None
    ):
        raise NotFoundError(f"Conversation {conversation_id} not found.")
    return conversation


AnonymousConversation = Annotated[Conversation, Depends(get_anonymous_conversation)]


@router.post("", response_model=AnonymousConversationRead, status_code=201)
async def create_anonymous_conversation(
    session: PublicDb, assistant: PublicAssistant
) -> AnonymousConversationRead:
    conversation = Conversation(tenant_id=assistant.tenant_id, assistant_id=assistant.id)
    session.add(conversation)
    await session.flush()

    await write_audit_log(
        session,
        tenant_id=assistant.tenant_id,
        action="conversation.create",
        resource_type="conversation",
        resource_id=conversation.id,
    )

    access_token = create_anonymous_session_token(conversation.id)
    return AnonymousConversationRead(conversation_id=conversation.id, access_token=access_token)


@router.post("/{conversation_id}/messages", response_model=MessageRead, status_code=201)
async def send_anonymous_message(
    body: MessageCreate,
    session: PublicDb,
    assistant: PublicAssistant,
    conversation: AnonymousConversation,
) -> MessageRead:
    assistant_message = await generate_assistant_reply(
        session, assistant.tenant_id, assistant, conversation, body.content
    )

    await write_audit_log(
        session,
        tenant_id=assistant.tenant_id,
        action="message.create",
        resource_type="message",
        resource_id=assistant_message.id,
    )
    return MessageRead.model_validate(assistant_message)


@router.post("/{conversation_id}/messages/stream")
async def send_anonymous_message_streaming(
    body: MessageCreate,
    session: PublicDb,
    assistant: PublicAssistant,
    conversation: AnonymousConversation,
) -> StreamingResponse:
    assistant_message = await generate_assistant_reply(
        session, assistant.tenant_id, assistant, conversation, body.content
    )

    await write_audit_log(
        session,
        tenant_id=assistant.tenant_id,
        action="message.create",
        resource_type="message",
        resource_id=assistant_message.id,
    )
    message_read = MessageRead.model_validate(assistant_message)

    return StreamingResponse(build_message_stream(message_read), media_type="text/event-stream")
