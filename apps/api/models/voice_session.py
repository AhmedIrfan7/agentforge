"""VoiceSession model (roadmap step 219, starts Milestone 8's data
layer). AGENTS.md's own "VOICE AGENT" section states outright: "The
Voice Agent should share conversation intelligence with the
Conversation Agent" -- so a voice session is deliberately NOT a
second, parallel transcript/message system. It's a real
`conversations.id` foreign key, one level under `Conversation` the
same way `Message` already sits under it: the real turns of a voice
call are persisted as ordinary `Message` rows (role="user"/
"assistant") through the exact same `message_processing.py:
generate_assistant_reply` pipeline text chat already uses (step 226's
own explicit job is wiring that path in) -- `VoiceSession` itself only
tracks the audio-CALL-specific lifecycle around that shared
conversation, not a duplicate of its content.

No `assistant_id`/`user_id` columns -- both are already reachable via
`conversation_id`'s own join, and duplicating them here would be
denormalization with no real read pattern asking for it yet, the same
"don't speculate about fields a real later step hasn't asked for"
discipline `Conversation` (176) and `KnowledgeBase` (082) both already
applied.

`ended_at` (nullable) is the one real lifecycle field this step's
literal scope needs: a `NULL` value means the session is still live,
a real timestamp means step 228's own "voice-session-end" endpoint
closed it -- no separate `status` column, since "ended or not" is
fully derivable from this one field (the same "derived, not stored
redundant state" reasoning `Invitation`'s own computed `status` field
already established for this codebase). `created_at` (from
`TimestampMixin`) IS the session's real start time -- a real voice
call's row is created at the moment it starts, so a separate
`started_at` column would just duplicate it.

No unique constraint on `conversation_id` -- a single ongoing
conversation can reasonably span more than one real voice call over
time (a visitor picks the phone back up later in the same support
thread), so one-to-many is the honest real shape, not artificially
one-to-one.

No provider/latency/transcript-specific fields yet -- those land with
the steps that actually need them (227 latency instrumentation, 228
transcript persistence is the shared `Message` table itself, not a new
column here).

Deliberately CASCADE on `conversation_id`'s delete -- a voice session
with no real conversation behind it is meaningless, same reasoning
`Message`'s own conversation FK already uses.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class VoiceSession(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "voice_sessions"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
