import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.knowledge_base import KnowledgeBase
from repositories.base import TenantScopedRepository


class KnowledgeBaseRepository(TenantScopedRepository[KnowledgeBase]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, KnowledgeBase)

    async def list_for_workspace(
        self, workspace_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[KnowledgeBase]:
        stmt = (
            select(KnowledgeBase)
            .where(
                KnowledgeBase.tenant_id == self.tenant_id,
                KnowledgeBase.workspace_id == workspace_id,
            )
            .order_by(KnowledgeBase.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_workspace(self, workspace_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(KnowledgeBase)
            .where(
                KnowledgeBase.tenant_id == self.tenant_id,
                KnowledgeBase.workspace_id == workspace_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
