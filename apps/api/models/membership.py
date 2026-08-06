"""Links a User to an Organization (and optionally a specific Workspace)
with a Role. Tenant-scoped: who belongs to an org is exactly the kind of
thing another tenant must never see — see
docs/adr/0003-multi-tenancy-isolation-strategy.md.

workspace_id is nullable on purpose: AGENTS.md describes both org-level
membership and workspace-specific assignment as real, distinct concepts
(not every member needs every workspace). A plain UniqueConstraint can't
express "unique per (tenant, user) when workspace_id IS NULL, unique per
(tenant, user, workspace) otherwise" — Postgres treats NULL != NULL in
unique constraints — so this uses two partial unique indexes instead.
"""

import uuid

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Membership(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        Index(
            "uq_memberships_org_level",
            "tenant_id",
            "user_id",
            unique=True,
            postgresql_where=text("workspace_id IS NULL"),
        ),
        Index(
            "uq_memberships_workspace_level",
            "tenant_id",
            "user_id",
            "workspace_id",
            unique=True,
            postgresql_where=text("workspace_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
