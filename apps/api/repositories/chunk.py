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
        self, knowledge_base_id: uuid.UUID, query: str, *, top_k: int = 10
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
        free-text query becomes a structured one."""
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
            .order_by(rank.desc())
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return [
            KeywordSearchResult(
                chunk_id=chunk.id, document_id=chunk.document_id, text=chunk.text, score=score
            )
            for chunk, score in result.all()
        ]

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
