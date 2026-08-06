"""Organization has no tenant_id — it IS the tenant root (ADR-0003), so it
doesn't fit TenantScopedRepository. Access control lives at the route
layer (routers/organization.py): who can see/create/delete an org is
resolved via Membership + RBAC (dependencies/tenant.py,
dependencies/rbac.py), not filtered here.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.membership import Membership
from models.organization import Organization


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> Organization | None:
        return await self.session.get(Organization, id)

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Organization]:
        """Only organizations this user has some membership in — the
        previous unrestricted "every organization in the system" listing
        was fine while nothing else had access control either, but would
        be a real tenant-isolation leak now that real users/auth exist."""
        stmt = (
            select(Organization)
            .join(Membership, Membership.tenant_id == Organization.id)
            .where(Membership.user_id == user_id)
            .distinct()
            .order_by(Organization.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(func.distinct(Organization.id)))
            .select_from(Organization)
            .join(Membership, Membership.tenant_id == Organization.id)
            .where(Membership.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, *, name: str, slug: str) -> Organization:
        org = Organization(name=name, slug=slug)
        self.session.add(org)
        await self.session.flush()
        return org

    async def delete(self, obj: Organization) -> None:
        await self.session.delete(obj)
