import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
