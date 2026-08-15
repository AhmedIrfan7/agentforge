import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.conversation import Conversation
from repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository[Conversation]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Conversation)

    async def list_for_assistant_and_user(
        self,
        assistant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Conversation]:
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.assistant_id == assistant_id,
                Conversation.user_id == user_id,
            )
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_assistant_and_user(
        self, assistant_id: uuid.UUID, user_id: uuid.UUID
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.assistant_id == assistant_id,
                Conversation.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
