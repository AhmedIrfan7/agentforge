"""First tenant-scoped table — see models/mixins.py:TenantScopedMixin and
docs/adr/0003-multi-tenancy-isolation-strategy.md."""

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Workspace(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        # Slug only needs to be unique within an organization, not globally.
        UniqueConstraint("tenant_id", "slug", name="uq_workspaces_tenant_id_slug"),
    )

    name: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(nullable=False)
