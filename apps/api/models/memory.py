"""Memory model (roadmap step 162, Milestone 5) -- the long-term,
Postgres-backed half of this codebase's memory system. AGENTS.md's own
"MEMORY ARCHITECTURE"/"MEMORY REQUIREMENTS" sections name several
memory types (short-term, long-term, user, session, organization,
assistant, workspace, agent) -- step 162's own parenthetical scopes
this model tightly to exactly five of them: short-term/long-term (a
persistence-tier column) and user/organization/session (a
who-does-this-belong-to column). Assistant/workspace/agent memory
aren't part of this step's own literal wording and have no real
caller yet.

`memory_type` genuinely supports both "short_term" and "long_term" as
values, but only "long_term" is ever written by real code today --
step 163's own "Redis-backed short-term memory store" is a
conversation-scoped, entirely separate Redis mechanism that never
touches this table; nothing in this codebase creates a Postgres row
tagged "short_term" yet. The column exists honestly as the full, real
taxonomy this subsystem's design commits to, not a speculative guess
-- same "field exists, only some values are currently reachable"
precedent `models/document.py`'s own `chunking_strategy_source`
already established.

`scope` distinguishes who a memory belongs to: "user" (`user_id`
populated), "session" (`session_id` populated), or "organization"
(neither -- `tenant_id`, already required on every row, already
identifies the organization; no second column needed).

As of step 176, `session_id` gets the real foreign key this docstring
originally promised: `models/conversation.py:Conversation` now exists,
so the "honestly-unconstrained column ahead of the table it will
eventually reference" (the same "field lands ahead of its full wiring"
precedent `AuditLog.actor_user_id` established for Milestone 2 before
auth existed) becomes a real, enforced reference, `CASCADE` on delete
-- same reasoning `Memory.user_id`'s own `CASCADE` already established:
a session-scoped memory has no reason to survive the conversation it
was scoped to.

As of step 164, `importance_score` lands: a plain `float`, app-level
convention 0.0 (negligible) to 1.0 (critical), no DB `CHECK` constraint
-- same "convention, not a hard constraint" choice `scope`/
`memory_type` already made rather than a Postgres enum. Defaults to
0.5 (neutral) since no real scorer exists yet -- step 165's own job
("Memory Agent logic: decide what deserves long-term retention") is to
compute a real score before a memory is even created, not to leave
this default in place; the default only matters for whatever creates a
`Memory` row before that logic exists (today, only tests).

As of step 168, `expires_at` lands: nullable, because
`memory_policy.py:compute_expiration`'s own real policy leaves it
`None` for high-importance memories -- "not everything deserves
permanent memory" (AGENTS.md's own "MEMORY LIFECYCLE" section) cuts
both ways, and something genuinely important should stay permanent,
not force-expire on a fixed schedule regardless of value. Computing a
real value is that policy module's job, not this column's -- same
"column here, real logic lives in its own module" split
`importance_score` (164) and `agents/memory.py:MemoryAgent` (165)
already established.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Memory(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "memories"

    scope: Mapped[str] = mapped_column(nullable=False)
    memory_type: Mapped[str] = mapped_column(nullable=False, default="long_term")
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True
    )
    content: Mapped[str] = mapped_column(nullable=False)
    importance_score: Mapped[float] = mapped_column(nullable=False, default=0.5)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
