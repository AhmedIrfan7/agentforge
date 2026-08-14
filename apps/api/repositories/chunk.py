import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.chunk import Chunk
from repositories.base import TenantScopedRepository


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
