"""Message model (roadmap step 177, Milestone 6) -- a single turn
within a `models/conversation.py:Conversation` (176). `role`/`content`
deliberately mirror `llm/base.py:Message`'s own field names (150) --
the exact shape a real chat call already needs to reconstruct a
prompt, not a parallel shape reinventing the same two fields. Stored
as a plain `str`, not `llm.base.Role`'s `Literal` -- same "convention,
not a hard DB constraint" choice `models/memory.py`'s own `scope`/
`memory_type` columns already made, since a Postgres enum would need
its own migration every time a new role value is ever needed.

Deliberately minimal beyond `conversation_id`/`role`/`content` -- same
"don't speculate about fields a real later step hasn't asked for yet"
discipline every model in this codebase already follows (`KnowledgeBase`
082, `Assistant` 159, `Conversation` 176). No `citations` (step 187's
own job), no `feedback` (189's own job), no token counts (no step
between here and 200 asks for them on a per-message basis the way
`agents/tracing.py`'s own per-request event already covers execution
tracing) -- each lands with the step that actually needs it.

`conversation_id` is `ondelete="CASCADE"` -- a message has no meaning
independent of the conversation it belongs to, the same "child has no
reason to outlive its parent" reasoning `Assistant.knowledge_base_id`
and `Memory.session_id` (as of 176) both already established.
"""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Message(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
