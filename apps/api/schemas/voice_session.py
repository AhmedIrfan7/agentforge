import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from schemas.message import MessageRead


class VoiceSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    ended_at: datetime | None
    created_at: datetime


class VoiceSessionEndRead(BaseModel):
    """Roadmap step 228's own end-session response -- reuses
    VoiceSessionRead wholesale plus the session's own real, exact
    transcript (`repositories/message.py:list_for_voice_session`), the
    same "reuse the already-real shape, don't invent a parallel one"
    reasoning `schemas/conversation.py:ConversationExportRead` already
    established for text chat's own export endpoint (191)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    ended_at: datetime | None
    created_at: datetime
    transcript: list[MessageRead]
