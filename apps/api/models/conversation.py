"""Conversation model (roadmap step 176, Milestone 6) -- the model
`models/memory.py:Memory.session_id` and `short_term_memory.py`'s own
`session_id` parameter have both been an unconstrained UUID waiting
for since Milestone 5 (each file's own docstring says so explicitly:
"no Conversation/ConversationSession model exists yet"). Sits under
`Assistant` in the product hierarchy (AGENTS.md's own "ORGANIZATION
STRUCTURE" diagram: ... AI Assistant(s) -> Specialized Agents -> Users
-> Conversations -> ...) -- the same "one parent FK, mirroring the
hierarchy" shape `Assistant` (159) itself established under
`KnowledgeBase`.

`user_id` is nullable and `SET NULL` on delete, not `CASCADE` --
deliberately different from `Memory.user_id`'s own `CASCADE` choice
(162): a user-scoped *memory* is inherently about that person and has
no reason to survive without them, but a conversation transcript is
closer to `AuditLog.actor_user_id`'s own reasoning (Milestone 2) --
a real record of what happened that should outlive the person who
triggered it, not vanish with their account. Nullable at all because a
real deployment channel (a public chat widget, AGENTS.md's own
"DEPLOYMENT CHANNELS" section) can have an anonymous visitor with no
platform `User` row -- `Assistant`/`Membership`'s own users, not a
widget's end user.

Deliberately minimal beyond `assistant_id`/`user_id` -- same "don't
speculate about fields a real later step hasn't asked for" discipline
`KnowledgeBase` (082) and `Assistant` (159) both already applied. No
`status` (step 181's own "conversation-state machine" is its explicit
owner), no `title` (step 184's own rename endpoint is what would need
one) -- both land with the step that actually needs them.

`models/memory.py:Memory.session_id` gains its real, promised foreign
key in this same step's migration -- the exact retrofit that model's
own step-162 docstring committed to once this table existed, not new
scope invented here.

As of step 181, `status` lands: the real, full six-value taxonomy the
roadmap step itself names ("new/active/waiting/processing/completed/
archived"), plain `str` not a Postgres enum -- same "convention, not a
hard DB constraint" choice `Memory.scope`/`memory_type` already made.
Real transition validation lives in `conversation_state.py`, not on
this model -- same "column here, real logic lives in its own module"
split `Memory.importance_score` (164) and `agents/memory.py:
MemoryAgent` (165) already established. Only `new` -> `active` (first
message sent) is wired into a real caller today
(`routers/conversation.py`); `waiting`/`processing`/`completed` are
real, legal states with no current writer -- `waiting` needs a
human-handoff/clarification mechanism this codebase doesn't have yet,
`processing` would need either background execution or a genuinely
safe intermediate-commit pattern inside a request-scoped session
(neither asked for by this step, and doing it carelessly is exactly
the class of bug steps 072/074/090 already found live), and
`completed` has no product signal for "this conversation is done" yet
-- `archived` is step 184's own explicit job. Same "field exists for
the real, full taxonomy; only some values are currently reachable"
precedent `Memory.memory_type`'s own "short_term" value already set.
"""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Conversation(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "conversations"

    assistant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assistants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(nullable=False, default="new")
