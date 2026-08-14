import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.document import Document
from repositories.base import TenantScopedRepository


class DocumentRepository(TenantScopedRepository[Document]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Document)

    async def list_for_knowledge_base(
        self, knowledge_base_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Document]:
        stmt = (
            select(Document)
            .where(
                Document.tenant_id == self.tenant_id,
                Document.knowledge_base_id == knowledge_base_id,
            )
            .order_by(Document.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_duplicates_in_knowledge_base(
        self, knowledge_base_id: uuid.UUID, content_hash: str, *, exclude_document_id: uuid.UUID
    ) -> Sequence[Document]:
        """Roadmap step 117 -- quality.py's own content_hash (step 096)
        is exactly the signal this queries against. Scoped to one
        knowledge base, matching the roadmap step's own wording ("within
        a knowledge base") rather than tenant-wide -- the same file
        genuinely uploaded into two different knowledge bases (e.g. a
        shared company policy doc) isn't the kind of accidental
        duplicate this step is meant to catch."""
        stmt = select(Document).where(
            Document.tenant_id == self.tenant_id,
            Document.knowledge_base_id == knowledge_base_id,
            Document.content_hash == content_hash,
            Document.id != exclude_document_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_knowledge_base(self, knowledge_base_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == self.tenant_id,
                Document.knowledge_base_id == knowledge_base_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
