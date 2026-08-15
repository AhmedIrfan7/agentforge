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
