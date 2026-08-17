import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models.api_key import ApiKey
from repositories.base import TenantScopedRepository


class ApiKeyRepository(TenantScopedRepository[ApiKey]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, ApiKey)
