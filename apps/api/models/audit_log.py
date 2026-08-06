"""Audit trail for tenant-scoped actions. tenant_id has no foreign key
constraint (unlike TenantScopedMixin's usual FK to organizations) so audit
history survives even if the organization itself is later deleted —
audit logs are exactly the kind of record that should outlive the thing
they're about. actor_user_id is nullable: no authenticated user exists
to attribute actions to until Milestone 2's auth lands (AGENTS.md
"Audit Logging" still wants every important action recorded even before
that; None here is honest about what's actually known today).
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
