import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.chunk import Chunk
from models.document import Document
from repositories.base import TenantScopedRepository


@dataclass(frozen=True)
class KeywordSearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    score: float


class ChunkRepository(TenantScopedRepository[Chunk]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Chunk)

    async def list_for_document(self, document_id: uuid.UUID) -> Sequence[Chunk]:
        stmt = (
            select(Chunk)
            .where(Chunk.tenant_id == self.tenant_id, Chunk.document_id == document_id)
            .order_by(Chunk.index)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_document(self, document_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.tenant_id == self.tenant_id, Chunk.document_id == document_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def search_by_keyword(
        self,
        knowledge_base_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        document_id: uuid.UUID | None = None,
        document_type: str | None = None,
    ) -> list[KeywordSearchResult]:
        """Roadmap step 121 -- Postgres full-text search against
        Chunk.search_vector (a DB-computed tsvector column, models/
        chunk.py), verified live before trusting the query shape:
        plainto_tsquery/ts_rank/@@ all compile and run correctly against
        the real chunks table through the least-privilege agentforge_app
        role, not just a superuser. Scoped the same way PgVectorStore.
        search() (step 119) is -- tenant_id app-layer filter plus a join
        through Document for knowledge_base_id, since Chunk has no
        knowledge_base_id column of its own. plainto_tsquery, not
        websearch_to_tsquery or a raw to_tsquery -- plain natural-
        language input (no operator syntax a caller would need to know),
        the same "don't ask more of a query string than a search box
        realistically gets" reasoning applies here as anywhere else a
        free-text query becomes a structured one.

        As of step 123, document_id/document_type are optional filters --
        same two fields, same reasoning, as vectorstore/base.py:
        SearchFilters (dense search's own equivalent), kept as plain
        keyword arguments here rather than a shared dataclass since
        this repository isn't a VectorStore implementation and doesn't
        need to satisfy that Protocol's exact shape."""
        ts_query = func.plainto_tsquery("english", query)
        rank = func.ts_rank(Chunk.search_vector, ts_query).label("rank")
        stmt = (
            select(Chunk, rank)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.tenant_id == self.tenant_id,
                Document.knowledge_base_id == knowledge_base_id,
                Chunk.search_vector.op("@@")(ts_query),
            )
        )
        if document_id is not None:
            stmt = stmt.where(Chunk.document_id == document_id)
        if document_type is not None:
            stmt = stmt.where(Document.doc_metadata["document_type"].astext == document_type)
        stmt = stmt.order_by(rank.desc()).limit(top_k)
        result = await self.session.execute(stmt)
        return [
            KeywordSearchResult(
                chunk_id=chunk.id, document_id=chunk.document_id, text=chunk.text, score=score
            )
            for chunk, score in result.all()
        ]

    async def get_expanded_context(self, chunk_id: uuid.UUID, *, window: int = 1) -> str:
        """Roadmap step 131 -- parent-child chunk retrieval, the
        "chunk window expansion" variant: rather than a separately
        stored, differently-sized "parent" chunk (a genuine schema
        change nothing else in this roadmap ever needs -- checked
        before choosing this), a matched chunk's "parent" context is
        reconstructed on the fly from its own real neighbors, using
        Chunk.index (the sequential position within its document,
        populated by every chunking strategy since step 105) and
        Chunk.document_id -- both already real, correct data, not new
        machinery. `window` chunks on each side, ordered back into
        their original document sequence and joined with a blank line,
        approximates the wider context a small, precisely-matched
        child chunk was originally embedded from.

        Raises for a nonexistent chunk_id rather than silently
        returning an empty string -- same "fail loud on a caller bug"
        precedent as citations.py's own dict-indexing choice (step 127)
        and PgVectorStore.upsert()'s (step 119)."""
        chunk = await self.get(chunk_id)
        if chunk is None:
            raise ValueError(f"cannot expand context for chunk {chunk_id}: it does not exist")

        stmt = (
            select(Chunk)
            .where(
                Chunk.tenant_id == self.tenant_id,
                Chunk.document_id == chunk.document_id,
                Chunk.index >= chunk.index - window,
                Chunk.index <= chunk.index + window,
            )
            .order_by(Chunk.index)
        )
        result = await self.session.execute(stmt)
        neighbors = result.scalars().all()
        return "\n\n".join(neighbor.text for neighbor in neighbors)

    async def count_embedded_for_document(self, document_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Chunk)
            .where(
                Chunk.tenant_id == self.tenant_id,
                Chunk.document_id == document_id,
                Chunk.embedding.is_not(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
