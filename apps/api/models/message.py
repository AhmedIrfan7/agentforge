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
082, `Assistant` 159, `Conversation` 176). No `feedback` (189's own
job), no token counts (no step between here and 200 asks for them on
a per-message basis the way `agents/tracing.py`'s own per-request
event already covers execution tracing) -- each lands with the step
that actually needs it.

`conversation_id` is `ondelete="CASCADE"` -- a message has no meaning
independent of the conversation it belongs to, the same "child has no
reason to outlive its parent" reasoning `Assistant.knowledge_base_id`
and `Memory.session_id` (as of 176) both already established.

As of step 183, `embedding`/`search_vector` land -- exactly
`models/chunk.py`'s own two-mechanism shape (nullable `pgvector.
sqlalchemy.Vector(1536)` for semantic search, a DB-`Computed` tsvector
for keyword search, same ivfflat-cosine / GIN index pair), reused
because step 183's own literal wording ("conversation search endpoint
(keyword+semantic)") is the identical two-mechanism problem Chunk
already solved -- no reason to invent a different shape for the same
problem one table over. `embedding` starts `None` (computed
asynchronously by `message_embedding.py`, dispatched right after a
message is created, same "exists before its embedding does" precedent
Chunk's own docstring already established at step 108); a message
created before that task completes is real but not yet semantically
searchable, the same honest, real, temporary gap `search_excludes_
chunks_without_embeddings_yet` already covers for Chunk.

As of step 187, `citations` lands: JSONB, a plain `list[dict[str,
object]]` (not a dict, unlike `Assistant.agent_configuration`/
`Document.doc_metadata`) -- a message can genuinely cite zero, one, or
several chunks, so a list is the honest shape, not a single dict with
speculative keys. Defaults to `[]`, not `None` -- a user message (no
retrieval behind it) and an assistant reply with nothing to cite are
both real, valid "no citations" states, not "not computed yet" ones;
`None` would conflate those. Written by `routers/conversation.py` as
`schemas/message.py:CitationRead.model_dump(mode="json")` dicts, not
raw `citations.py:Citation` dataclasses -- `Citation.chunk_id`/
`document_id` are `uuid.UUID`, and neither Postgres's JSONB codec nor
plain `json.dumps` knows how to serialize those; routing through a
Pydantic model's own `mode="json"` dump (which converts UUIDs to
strings automatically) sidesteps that without inventing a custom JSON
encoder for one column.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin

EMBEDDING_DIMENSIONS = 1536


class Message(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index(
            "ix_messages_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_messages_search_vector_gin", "search_vector", postgresql_using="gin"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True), nullable=False
    )
    citations: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
