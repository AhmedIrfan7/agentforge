import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models.invitation import Invitation
from repositories.base import TenantScopedRepository


class InvitationRepository(TenantScopedRepository[Invitation]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Invitation)
