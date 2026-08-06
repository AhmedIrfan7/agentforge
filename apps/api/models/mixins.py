"""Shared model mixins.

UUID primary keys (not sequential integers) so IDs are non-guessable —
sequential org/workspace IDs would let one tenant estimate another
tenant's ID space, which is exactly the kind of cross-tenant information
leak AGENTS.md SECTION 9 calls out.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantScopedMixin:
    """Every tenant-scoped table gets this. See
    docs/adr/0003-multi-tenancy-isolation-strategy.md — tenant_id here is
    one layer of defense-in-depth; Postgres Row-Level Security (enabled per
    table via Alembic migration) is the other, so a forgotten application
    query filter still can't leak across tenants.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805  SQLAlchemy declared_attr convention
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class TenantScopedEntity(UUIDPrimaryKeyMixin, TenantScopedMixin):
    """Combines the two mixins above so repositories/base.py can bind its
    generic type parameter to a real class. A structural Protocol with
    plain `id: uuid.UUID` / `tenant_id: uuid.UUID` attributes doesn't
    reliably match SQLAlchemy's Mapped[] descriptors (InstrumentedAttribute
    at the class level vs. a plain value at the instance level) — binding
    to this class instead sidesteps that entirely.
    """
