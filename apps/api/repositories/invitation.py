import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import set_lookup_token_hash
from models.invitation import Invitation
from repositories.base import TenantScopedRepository


class InvitationRepository(TenantScopedRepository[Invitation]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Invitation)


async def get_invitation_by_token_hash(session: AsyncSession, token_hash: str) -> Invitation | None:
    """Not tenant-scoped — same reason repositories/rbac.py's helpers
    aren't: this runs before any tenant context exists, since the token
    itself is what identifies the tenant. See db.py:set_lookup_token_hash
    and migrations/versions/*_add_invitation_by_token_rls_policy.py."""
    await set_lookup_token_hash(session, token_hash)
    result = await session.execute(select(Invitation).where(Invitation.token_hash == token_hash))
    return result.scalar_one_or_none()
