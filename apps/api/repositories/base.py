"""Base repository for tenant-scoped models.

Every query here filters by tenant_id explicitly, in the application
layer — on top of, not instead of, Postgres Row-Level Security. This is
the app-layer half of the defense-in-depth ADR-0003 calls for: RLS is
what makes a forgotten filter here fail safe rather than leak data, but
the filter still belongs here too, so a bug shows up as "no rows found"
in a test long before anyone has to rely on RLS catching it in production.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.mixins import TenantScopedEntity


class TenantScopedRepository[ModelT: TenantScopedEntity]:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, model: type[ModelT]) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.model = model

    async def get(self, id: uuid.UUID) -> ModelT | None:
        stmt = select(self.model).where(
            self.model.id == id,
            self.model.tenant_id == self.tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[ModelT]:
        stmt = (
            select(self.model)
            .where(self.model.tenant_id == self.tenant_id)
            .order_by(self.model.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.tenant_id == self.tenant_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, **fields: Any) -> ModelT:
        # tenant_id is always this repository's own — never accepted from
        # fields, so a caller can't (accidentally or otherwise) create a
        # row tagged as a different tenant. Postgres RLS's WITH CHECK
        # would reject it anyway, but failing here is a clearer error
        # than a database exception three layers down.
        fields.pop("tenant_id", None)
        obj = self.model(tenant_id=self.tenant_id, **fields)  # type: ignore[call-arg]
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
