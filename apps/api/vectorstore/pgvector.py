"""PgVectorStore (roadmap step 119) -- the real, and only, VectorStore
implementation this roadmap ever builds (checked at step 118: no second
vector-store step exists anywhere in docs/ROADMAP.md). Wraps the
already-existing `chunks` table (models/chunk.py, steps 105/108/109)
and its ivfflat index (steps 109/110) behind vectorstore/base.py:
VectorStore -- no new schema, no new migration, this step is purely
adapter code.

search() uses pgvector-python's own SQLAlchemy integration
(Chunk.embedding.cosine_distance(...)), verified live against real
Postgres before trusting it -- confirmed it compiles to the real `<=>`
operator ix_chunks_embedding_ivfflat's own vector_cosine_ops expects,
not a guess at pgvector-python's API surface. Scoped by tenant_id (an
app-layer filter, same defense-in-depth reasoning every repository in
this project already applies on top of RLS) and knowledge_base_id via a
join through Document, since Chunk itself has no knowledge_base_id
column of its own -- only document_id.

Uses db.py:get_worker_session (NullPool), not get_session -- this
provider has no fixed caller yet (step 120's retrieval endpoint is the
first), so it can't assume a single persistent event loop the way
get_session's pooled engine requires. get_worker_session is documented
in db.py as safe for "any process that creates a new event loop per
unit of work," which covers a Celery task AND a FastAPI request handler
alike -- not just literal Celery workers despite the name.

upsert()'s real, honest limitation: VectorRecord (vectorstore/base.py)
deliberately doesn't carry start/end/index, since those are pgvector-
adapter-specific implementation details, not something every possible
vector store backend has a concept of -- but Chunk's own table requires
them (NOT NULL). This adapter's upsert() is therefore update-only in
practice: it can update an EXISTING Chunk row's text/embedding by id,
but can't create a brand-new one from a VectorRecord alone. Nothing in
this roadmap ever calls upsert() to create a chunk from scratch outside
embeddings_pipeline.py's own dispatch (which knows start/end/index from
the real chunking algorithm) -- documented as a real, deliberate
adapter limitation rather than weakening Chunk's own NOT NULL columns
to accommodate a caller that doesn't exist yet.

As of step 123, search() applies SearchFilters.document_type via
Document.doc_metadata["document_type"].astext -- verified live before
trusting it (SQLAlchemy's JSONB accessor + .astext compiles to the real
Postgres ->> operator). document_id filters directly on Chunk.
document_id, no JSONB involved.
"""

import uuid

from sqlalchemy import select

from db import get_worker_session, set_tenant_context
from models.chunk import Chunk
from models.document import Document
from vectorstore.base import SearchFilters, VectorRecord, VectorSearchResult


class PgVectorStore:
    name = "pgvector"

    async def upsert(
        self, tenant_id: uuid.UUID, knowledge_base_id: uuid.UUID, records: list[VectorRecord]
    ) -> None:
        async with get_worker_session() as session:
            await set_tenant_context(session, tenant_id)
            for record in records:
                chunk = await session.get(Chunk, record.id)
                if chunk is None:
                    raise ValueError(
                        f"PgVectorStore.upsert cannot create chunk {record.id} -- no "
                        "existing row to update, and VectorRecord doesn't carry the "
                        "start/end/index a new Chunk row requires. See this module's "
                        "own docstring."
                    )
                chunk.text = record.text
                chunk.embedding = record.embedding
            await session.commit()

    async def search(
        self,
        tenant_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        query_vector: list[float],
        *,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[VectorSearchResult]:
        async with get_worker_session() as session:
            await set_tenant_context(session, tenant_id)
            stmt = (
                select(Chunk, Chunk.embedding.cosine_distance(query_vector).label("distance"))
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    Chunk.tenant_id == tenant_id,
                    Document.knowledge_base_id == knowledge_base_id,
                    Chunk.embedding.is_not(None),
                )
            )
            if filters is not None:
                if filters.document_id is not None:
                    stmt = stmt.where(Chunk.document_id == filters.document_id)
                if filters.document_type is not None:
                    stmt = stmt.where(
                        Document.doc_metadata["document_type"].astext == filters.document_type
                    )
            stmt = stmt.order_by(Chunk.embedding.cosine_distance(query_vector)).limit(top_k)
            result = await session.execute(stmt)
            return [
                VectorSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    score=1.0 - distance,  # cosine_distance -> cosine similarity
                )
                for chunk, distance in result.all()
            ]
