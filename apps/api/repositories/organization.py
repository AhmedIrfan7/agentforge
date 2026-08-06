"""Organization has no tenant_id — it IS the tenant root (ADR-0003), so it
doesn't fit TenantScopedRepository. No access control exists yet either:
these endpoints are wide open until Milestone 2's auth lands (roadmap
steps 060+) — see routers/organization.py for the same caveat spelled out
where it's actually exposed over HTTP.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.organization import Organization


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> Organization | None:
        return await self.session.get(Organization, id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[Organization]:
        stmt = select(Organization).order_by(Organization.id).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(Organization))
        return result.scalar_one()

    async def create(self, *, name: str, slug: str) -> Organization:
        org = Organization(name=name, slug=slug)
        self.session.add(org)
        await self.session.flush()
        return org

    async def delete(self, obj: Organization) -> None:
        await self.session.delete(obj)
