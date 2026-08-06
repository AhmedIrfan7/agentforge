import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models.workspace import Workspace
from repositories.base import TenantScopedRepository


class WorkspaceRepository(TenantScopedRepository[Workspace]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Workspace)
