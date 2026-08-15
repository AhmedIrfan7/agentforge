import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from schemas.memory import MemoryRead
from schemas.message import MessageRead


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    assistant_id: uuid.UUID
    user_id: uuid.UUID | None
    status: str
    title: str | None
    is_pinned: bool
    created_at: datetime
    updated_at: datetime


class ConversationUpdate(BaseModel):
    """Partial update (roadmap step 184's "rename/pin" endpoints,
    folded into one PATCH) -- same `model_fields_set`-driven "only
    fields the caller actually included get applied" pattern
    routers/security_settings.py:update_security_settings already
    established, so an omitted field stays untouched and an explicit
    `null` for `title` really does clear it."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None


class ConversationExportRead(BaseModel):
    """Roadmap step 191's own JSON export shape -- reuses ConversationRead/
    MessageRead wholesale rather than inventing a third representation
    of the same data; the markdown export (routers/conversation.py's
    own _render_conversation_markdown) is built from these same two
    already-real shapes too, not a separate query."""

    conversation: ConversationRead
    messages: list[MessageRead]


class AnonymousConversationRead(BaseModel):
    """Roadmap step 192's own creation response -- deliberately NOT
    ConversationRead: an anonymous caller has no session/RBAC context
    to ever fetch this conversation any other way, so `access_token`
    (routers/public_conversation.py's own anonymous session JWT) is
    the actual, load-bearing payload here, not a nice-to-have extra
    field. No `tenant_id`/`status`/etc. -- a pre-auth visitor has no
    use for them and no other endpoint that would need to correlate
    them against anything."""

    conversation_id: uuid.UUID
    access_token: str


class ConversationClaimRequest(BaseModel):
    """Roadmap step 193's own claim request -- the ONLY input a
    newly-identified (real, authenticated) caller needs to supply.
    `conversation_id` is deliberately NOT a body/path field here: the
    anonymous session token itself already names exactly one
    conversation (auth/jwt.py:decode_anonymous_session_token), so
    accepting a second, independent conversation_id would just be a
    value that has to be checked against the token's own for
    agreement -- routers/public_conversation.py's own `get_anonymous_
    conversation` rejected that same redundancy already."""

    anonymous_token: str


class ConversationClaimRead(BaseModel):
    """AGENTS.md's own "USER IDENTIFICATION" section lists "Relevant
    memories"/"Saved context" among the things a newly-identified user
    should be reconnected with -- returned here directly in the claim
    response rather than silently injected into a future orchestrator
    call, since no chat UI or orchestrator signature change exists yet
    that could consume it; a client surfaces these, the same way the
    section's own examples read (a user-facing reconnection, not a
    hidden prompt-engineering detail)."""

    conversation: ConversationRead
    memories: list[MemoryRead]
