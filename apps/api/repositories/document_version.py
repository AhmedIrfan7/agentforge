import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.document_version import DocumentVersion
from repositories.base import TenantScopedRepository


class DocumentVersionRepository(TenantScopedRepository[DocumentVersion]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, DocumentVersion)

    async def list_for_document(
        self, document_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[DocumentVersion]:
        stmt = (
            select(DocumentVersion)
            .where(
                DocumentVersion.tenant_id == self.tenant_id,
                DocumentVersion.document_id == document_id,
            )
            .order_by(DocumentVersion.version_number.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_all_for_document(self, document_id: uuid.UUID) -> Sequence[DocumentVersion]:
        """Unpaginated, unlike list_for_document above -- roadmap step
        116's deletion cleanup needs every historical storage_key, not
        just one page of them; a document with more than list_for_
        document's default 50-row page could otherwise leak storage
        objects belonging to versions past that page."""
        stmt = select(DocumentVersion).where(
            DocumentVersion.tenant_id == self.tenant_id,
            DocumentVersion.document_id == document_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_document(self, document_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(DocumentVersion)
            .where(
                DocumentVersion.tenant_id == self.tenant_id,
                DocumentVersion.document_id == document_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
