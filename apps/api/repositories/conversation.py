import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models.conversation import Conversation
from repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository[Conversation]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Conversation)
