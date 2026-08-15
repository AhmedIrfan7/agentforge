"""Postgres-backed long-term memory store (roadmap step 164) --
`MemoryRepository` is the real access layer `models/memory.py:Memory`
(162) needed: query methods for each of that model's three real
scopes, ordered by `importance_score` (162's own deferred column,
added by this step's migration) descending -- the whole point of
"importance-scored" is that a caller retrieving memory gets the most
important entries first, not insertion order. `min_importance` lets a
caller filter out low-value memories entirely; the default (0.0)
matches every entry, so existing behavior is unchanged for a caller
that doesn't pass it.

Computing a real importance score is deliberately NOT this step's job
-- step 165 ("Memory Agent logic: decide what deserves long-term
retention") owns that decision; this repository only stores and
retrieves by whatever score a caller (eventually the Memory Agent)
provides.

As of step 169, `list_all_for_user` adds real "export my own data"
semantics -- unlike `list_for_user`, it takes no `limit`/`min_importance`
(a data-portability export means genuinely everything the user owns,
not a caller-chosen page or importance cutoff) and orders
chronologically rather than by importance, matching how a person
actually reviews their own exported history.

As of step 170, `delete_all_for_user` adds the real "right to erasure"
operation -- one `DELETE` statement, not a fetch-then-delete-each loop,
since a bulk erasure has no reason to round-trip every row through
Python first. Returns the real deleted count (via `RETURNING`) so the
caller (`routers/memory.py`) can record a meaningful, non-empty audit
log entry even though there's no single `resource_id` a bulk operation
naturally has.

As of step 173, `update_content` adds this repository's first real
update path -- every prior write was a `create` or a `delete`; nothing
before now had a real reason to mutate an existing row in place.
`memory_conflict.py`'s conflict-resolution logic (173) is that reason:
a new memory that conflicts with and outscores an existing one
replaces its content/score/expiration rather than creating a
duplicate.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.memory import Memory
from repositories.base import TenantScopedRepository


class MemoryRepository(TenantScopedRepository[Memory]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Memory)

    async def list_for_user(
        self, user_id: uuid.UUID, *, min_importance: float = 0.0, limit: int = 50, offset: int = 0
    ) -> Sequence[Memory]:
        stmt = (
            select(Memory)
            .where(
                Memory.tenant_id == self.tenant_id,
                Memory.scope == "user",
                Memory.user_id == user_id,
                Memory.importance_score >= min_importance,
            )
            .order_by(Memory.importance_score.desc(), Memory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Memory)
            .where(
                Memory.tenant_id == self.tenant_id,
                Memory.scope == "user",
                Memory.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_all_for_user(self, user_id: uuid.UUID) -> Sequence[Memory]:
        stmt = (
            select(Memory)
            .where(
                Memory.tenant_id == self.tenant_id,
                Memory.scope == "user",
                Memory.user_id == user_id,
            )
            .order_by(Memory.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            delete(Memory)
            .where(
                Memory.tenant_id == self.tenant_id,
                Memory.scope == "user",
                Memory.user_id == user_id,
            )
            .returning(Memory.id)
        )
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def update_content(
        self,
        memory: Memory,
        *,
        content: str,
        importance_score: float,
        expires_at: datetime | None,
    ) -> Memory:
        memory.content = content
        memory.importance_score = importance_score
        memory.expires_at = expires_at
        await self.session.flush()
        return memory

    async def list_for_organization(
        self, *, min_importance: float = 0.0, limit: int = 50, offset: int = 0
    ) -> Sequence[Memory]:
        stmt = (
            select(Memory)
            .where(
                Memory.tenant_id == self.tenant_id,
                Memory.scope == "organization",
                Memory.importance_score >= min_importance,
            )
            .order_by(Memory.importance_score.desc(), Memory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_for_session(
        self,
        session_id: uuid.UUID,
        *,
        min_importance: float = 0.0,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Memory]:
        stmt = (
            select(Memory)
            .where(
                Memory.tenant_id == self.tenant_id,
                Memory.scope == "session",
                Memory.session_id == session_id,
                Memory.importance_score >= min_importance,
            )
            .order_by(Memory.importance_score.desc(), Memory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
