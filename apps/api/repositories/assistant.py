import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.assistant import Assistant
from repositories.base import TenantScopedRepository


class AssistantRepository(TenantScopedRepository[Assistant]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Assistant)

    async def list_for_knowledge_base(
        self, knowledge_base_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Assistant]:
        stmt = (
            select(Assistant)
            .where(
                Assistant.tenant_id == self.tenant_id,
                Assistant.knowledge_base_id == knowledge_base_id,
            )
            .order_by(Assistant.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_knowledge_base(self, knowledge_base_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Assistant)
            .where(
                Assistant.tenant_id == self.tenant_id,
                Assistant.knowledge_base_id == knowledge_base_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
