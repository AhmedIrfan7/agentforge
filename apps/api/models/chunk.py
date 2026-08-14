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

`embedding` (added at step 108, folding in step 109's own literal task
early -- see embeddings_pipeline.py's module docstring for why) is
`pgvector.sqlalchemy.Vector(1536)`, nullable: a Chunk exists the moment
its text/start/end/index are known, before an embedding is computed for
it, so the column can't be NOT NULL. 1536 is `embeddings.openai
.OpenAIEmbeddingProvider.dimensions` exactly (text-embedding-3-small's
native output size) -- the only real provider this roadmap ever adds
behind `EmbeddingProvider` (checked: no second embedding-provider step
exists anywhere in docs/ROADMAP.md), so there's no speculative
multi-provider dimension mismatch to design around here.

Step 105's own gap ("nothing dispatches chunking yet") is closed as of
step 108: embeddings_pipeline.py creates real Chunk rows from a
Document's extracted_text + chunking_strategy, immediately followed by
embedding generation in the same task.

(document_id, index) is unique -- two chunks can't legitimately occupy
the same position within one document; re-chunking a document (a
future concern, not this step's) would need to replace its old chunks
outright, not create a second, colliding index 0.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin

EMBEDDING_DIMENSIONS = 1536


class Chunk(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "index", name="uq_chunks_document_id_index"),
        # ivfflat, not hnsw: this project's default choice for a first
        # ANN index -- cheaper to build and good enough at the row counts
        # a real deployment starts at; step 110 ("background task: vector
        # indexing") owns rebuilding/tuning this as data grows, not this
        # migration's job to get right forever. Cosine ops since that's
        # the distance OpenAI's own embeddings are meant to be compared
        # with (verified against OpenAI's docs, same as embeddings/
        # openai.py's own model choice).
        Index(
            "ix_chunks_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

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
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
