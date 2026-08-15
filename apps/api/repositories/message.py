import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models.message import Message
from repositories.base import TenantScopedRepository


class MessageRepository(TenantScopedRepository[Message]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Message)
