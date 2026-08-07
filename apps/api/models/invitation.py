"""An invite to join an organization, sent to an email address that may
not have an AgentForge account yet (unlike Membership, which links an
existing User). Tenant-scoped: who's been invited into an org is exactly
the kind of thing another tenant must never see, same reasoning as
Membership.

workspace_id is nullable for the same reason as Membership's: an invite
can grant org-level access or be scoped to one workspace.

accepted_at/revoked_at (not a single status enum) mirrors Session's
revoked_at pattern — a plain nullable timestamp says both "did it happen"
and "when," and a third state (expired) is derived from expires_at rather
than stored, so there's nothing to keep in sync.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Invitation(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "invitations"
    __table_args__ = (
        # Only one *pending* invite per (tenant, email) — an already
        # accepted or revoked invitation doesn't block re-inviting the
        # same address, so this can't be a plain unique constraint.
        Index(
            "uq_invitations_pending_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    email: Mapped[str] = mapped_column(nullable=False, index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
