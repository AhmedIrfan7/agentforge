import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
