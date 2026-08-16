import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.membership import Membership
from models.role import Role
from models.user import User
from repositories.base import TenantScopedRepository


class MembershipRepository(TenantScopedRepository[Membership]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Membership)

    async def list_org_level_with_user_and_role(
        self, *, limit: int = 50, offset: int = 0
    ) -> Sequence[tuple[Membership, User, Role]]:
        """Org-level membership only (workspace_id IS NULL) -- see
        models/membership.py's own docstring for why workspace-specific
        assignment is a real, separate concept this doesn't touch."""
        stmt = (
            select(Membership, User, Role)
            .join(User, User.id == Membership.user_id)
            .join(Role, Role.id == Membership.role_id)
            .where(Membership.tenant_id == self.tenant_id, Membership.workspace_id.is_(None))
            .order_by(User.email)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def count_org_level(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Membership)
            .where(Membership.tenant_id == self.tenant_id, Membership.workspace_id.is_(None))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_org_owners(self, org_owner_role_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.tenant_id == self.tenant_id,
                Membership.workspace_id.is_(None),
                Membership.role_id == org_owner_role_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
