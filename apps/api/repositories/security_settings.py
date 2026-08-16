import uuid
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.security_settings import SecuritySettings
from repositories.base import TenantScopedRepository


def origin_is_allowed(origin: str, allowed_domains: list[str]) -> bool:
    """Real hostname match against `SecuritySettings.allowed_domains`
    (subdomains of an allowed domain implicitly allowed) -- promoted
    here from `routers/public_conversation.py`'s own private
    `_origin_is_allowed` (step 208) once `routers/public_voice.py`
    (221) became a genuine second real caller needing the identical
    check, the same "share once a real second caller exists" bar this
    codebase applies everywhere else."""
    hostname = urlparse(origin).hostname
    if not hostname:
        return False
    hostname = hostname.lower()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in (raw.lower().strip() for raw in allowed_domains)
    )


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
