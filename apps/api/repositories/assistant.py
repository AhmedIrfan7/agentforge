import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import set_lookup_assistant_id
from models.assistant import Assistant
from repositories.base import TenantScopedRepository


async def get_public_assistant_by_id(
    session: AsyncSession, assistant_id: uuid.UUID
) -> Assistant | None:
    """Not tenant-scoped -- same reason repositories/invitation.py:
    get_invitation_by_token_hash isn't: this runs before any tenant
    context exists, since assistant_id is what identifies the tenant.
    See db.py:set_lookup_assistant_id and migrations/versions/*_add_
    assistant_by_id_rls_policy_for_.py.

    Checks is_public=True itself, in the application layer, on top of
    the RLS policy that only makes the row visible enough to check --
    same "app-layer filter on top of, not instead of, RLS" defense-in-
    depth reasoning repositories/base.py's own module docstring already
    states for the ordinary tenant-scoped case. A real (non-public)
    Assistant existing at this id is not something an anonymous caller
    should be able to distinguish from "no such assistant" -- returning
    None either way, not a different error, matches every other
    "don't leak existence" 404 in this codebase."""
    await set_lookup_assistant_id(session, assistant_id)
    result = await session.execute(select(Assistant).where(Assistant.id == assistant_id))
    assistant = result.scalar_one_or_none()
    if assistant is None or not assistant.is_public:
        return None
    return assistant


class AssistantRepository(TenantScopedRepository[Assistant]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Assistant)

    async def list_for_knowledge_base(
        self, knowledge_base_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Assistant]:
        stmt = (
            select(Assistant)
            .where(
                Assistant.tenant_id == self.tenant_id,
                Assistant.knowledge_base_id == knowledge_base_id,
            )
            .order_by(Assistant.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_knowledge_base(self, knowledge_base_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Assistant)
            .where(
                Assistant.tenant_id == self.tenant_id,
                Assistant.knowledge_base_id == knowledge_base_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
