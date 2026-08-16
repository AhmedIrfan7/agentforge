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

`rate_limit_public_message_send` (step 199) gates `send_anonymous_
message`/`send_anonymous_message_streaming`, keyed by `assistant.
tenant_id` -- the only real tenant identity a caller with no JWT and no
Membership can offer. Shares its Redis key prefix and budget with
`routers/conversation.py:rate_limit_message_send` on purpose: an org's
real per-tenant limit is the same real cost (an LLM call) regardless of
whether it arrived through this zero-auth door or the authenticated
one, and this door is the more abuse-prone of the two -- reachable
with zero signup friction, the exact "prompt flooding"/"resource
exhaustion" scenario AGENTS.md's own "ABUSE PREVENTION" section names.

As of step 220, `POST .../{conversation_id}/voice-sessions` starts a
real `VoiceSession` (219) under an already-existing anonymous
conversation -- deliberately NOT a second, parallel "create a
conversation for voice" endpoint. A real caller first gets an
anonymous conversation + token the exact same way text chat already
does (`create_anonymous_conversation`, above), then starts a voice
session under it; this reuses `AnonymousConversation`'s own auth
dependency wholesale, so a voice call is authorized by the identical
anonymous-session-token mechanism, not a second one. This also directly
realizes the reason step 219's own `VoiceSession` model deliberately
put NO unique constraint on `conversation_id`: the same visitor could
start a fresh voice session on an existing conversation more than once
(picking the call back up later), or a conversation that began as text
chat could add voice mid-thread -- "shares conversation intelligence
with the Conversation Agent" (AGENTS.md's own "VOICE AGENT" section) is
what this design is actually for. No authenticated-side equivalent
exists yet -- this milestone's own roadmap sequence (216-232) names
only one "voice-session-start" step, and `apps/widget` (Milestone 7's
real, only public-facing consumer so far) is anonymous-only anyway;
building an authenticated one now, with no dashboard UI to call it and
no roadmap step asking for it, would be speculative.

`get_public_assistant` (step 208) also enforces the org's own
`SecuritySettings.allowed_domains` (AGENTS.md's own "SECURITY
SETTINGS" section names "Allowed domains" verbatim) -- the single
resolution point every endpoint in this router already goes through
for `is_public`, so checking domain restriction here covers all three
uniformly rather than wiring a second dependency into each route.
Empty `allowed_domains` (the default) means no restriction -- every
existing public assistant/embed keeps working unchanged. Matched
against the request's real `Origin` header (hostname, case-
insensitive, subdomains of an allowed domain implicitly allowed) --
this is a real, honest CORS-adjacent check, not the browser-enforced
CORS policy itself (`main.py`'s own wildcard `CORSMiddleware` stays
global; FastAPI's CORSMiddleware has no per-request dynamic-origin
support, and a pure CORS header can't meaningfully stop a non-browser
caller anyway). **Honest, tracked limitation, not silently worked
around:** a request with NO Origin header (any non-browser HTTP
client, or a server-side proxy that strips it) is allowed through
regardless of `allowed_domains` -- this feature constrains BROWSER-
based embedding on an unauthorized site, the real threat AGENTS.md's
own "ABUSE PREVENTION" section names, not a general API firewall
against a caller who already has a valid `assistant_id` and is willing
to spoof or omit headers; every real product's own "allowed domains"
feature has this identical, well-understood limitation.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from auth.jwt import TokenError, create_anonymous_session_token, decode_anonymous_session_token
from db import set_tenant_context
from dependencies.db import get_db
from errors import ForbiddenError, NotFoundError, UnauthorizedError
from message_processing import build_message_stream, generate_assistant_reply
from models.assistant import Assistant
from models.conversation import Conversation
from rate_limit import MESSAGE_SEND_RATE_LIMIT, check_rate_limit
from repositories.assistant import get_public_assistant_by_id
from repositories.conversation import ConversationRepository
from repositories.security_settings import SecuritySettingsRepository, origin_is_allowed
from repositories.voice_session import VoiceSessionRepository
from schemas.conversation import AnonymousConversationRead
from schemas.message import MessageCreate, MessageRead
from schemas.voice_session import VoiceSessionRead

router = APIRouter(prefix="/public/assistants/{assistant_id}/conversations", tags=["public-chat"])

PublicDb = Annotated[AsyncSession, Depends(get_db)]

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_public_assistant(
    assistant_id: uuid.UUID, session: PublicDb, request: Request
) -> Assistant:
    assistant = await get_public_assistant_by_id(session, assistant_id)
    if assistant is None:
        raise NotFoundError(f"Assistant {assistant_id} not found.")
    await set_tenant_context(session, assistant.tenant_id)

    security_settings = await SecuritySettingsRepository(
        session, assistant.tenant_id
    ).get_singleton()
    origin = request.headers.get("origin")
    allowed_domains = security_settings.allowed_domains if security_settings else []
    if allowed_domains and origin and not origin_is_allowed(origin, allowed_domains):
        raise ForbiddenError("This assistant is not permitted to be embedded on this domain.")

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


async def rate_limit_public_message_send(assistant: PublicAssistant) -> None:
    await check_rate_limit(
        f"message_send:{assistant.tenant_id}", limit=MESSAGE_SEND_RATE_LIMIT, window_seconds=60
    )


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


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=201,
    dependencies=[Depends(rate_limit_public_message_send)],
)
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


@router.post(
    "/{conversation_id}/messages/stream",
    dependencies=[Depends(rate_limit_public_message_send)],
)
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


@router.post(
    "/{conversation_id}/voice-sessions",
    response_model=VoiceSessionRead,
    status_code=201,
)
async def start_voice_session(
    session: PublicDb, assistant: PublicAssistant, conversation: AnonymousConversation
) -> VoiceSessionRead:
    repo = VoiceSessionRepository(session, assistant.tenant_id)
    voice_session = await repo.create(conversation_id=conversation.id)

    await write_audit_log(
        session,
        tenant_id=assistant.tenant_id,
        action="voice_session.create",
        resource_type="voice_session",
        resource_id=voice_session.id,
    )
    return VoiceSessionRead.model_validate(voice_session)
