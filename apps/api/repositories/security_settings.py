import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.security_settings import SecuritySettings
from repositories.base import TenantScopedRepository


class SecuritySettingsRepository(TenantScopedRepository[SecuritySettings]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, SecuritySettings)

    async def get_singleton(self) -> SecuritySettings | None:
        """The one row for this tenant (routers/organization.py auto-
        creates it alongside the organization) — a dedicated method
        rather than list()[0], since "the settings row" isn't really a
        paginated collection."""
        result = await self.session.execute(
            select(SecuritySettings).where(SecuritySettings.tenant_id == self.tenant_id)
        )
        return result.scalar_one_or_none()
