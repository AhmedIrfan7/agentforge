"""Chunk model (roadmap step 105) -- what every pure chunking algorithm
since step 098 (chunking_fixed_size.py through chunking_recursive_
hybrid.py, chosen per document via Document.chunking_strategy, step 104)
has been building toward: the persisted output of actually running one
of them against a document's extracted_text.

Mirrors chunking_types.py:Chunk's own shape exactly (text/start/end/
index) plus the tenant-scoping and document association every other
persisted entity in this pipeline needs -- start/end are character
offsets into the owning Document's extracted_text, the same contract
every chunker already guarantees (chunk.text == extracted_text[start:end]
for every strategy except chunking_markdown_heading.py/chunking_
recursive_hybrid.py's own documented, narrow exception for a sub-split
oversized section's later pieces).

No embedding-related columns yet (vector, embedding model, etc.) --
those are steps 106-109's job (embedding-provider abstraction, the
provider implementation, batched generation, the pgvector column
itself), the same "add the field when the step that needs it lands"
discipline already used throughout this project (Document's own
storage_key/content_type/size_bytes were deferred from step 083 to 084
for the identical reason).

Real, honest gap this step doesn't close: nothing actually DISPATCHES
chunking yet -- no code path creates a Chunk row from a Document's
extracted_text and its chunking_strategy. The roadmap has no step
between this one and 108 ("background task: batched embedding
generation") dedicated to that dispatch; 108 is the first step whose
own description implies chunks already exist to embed. Tracked here
explicitly rather than silently assumed away -- whoever picks up 106+
needs to either find that dispatch already exists by then or build it
as part of getting embeddings generated.

(document_id, index) is unique -- two chunks can't legitimately occupy
the same position within one document; re-chunking a document (a
future concern, not this step's) would need to replace its old chunks
outright, not create a second, colliding index 0.
"""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Chunk(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "index", name="uq_chunks_document_id_index"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(nullable=False)
    start: Mapped[int] = mapped_column(nullable=False)
    end: Mapped[int] = mapped_column(nullable=False)
    index: Mapped[int] = mapped_column(nullable=False)
