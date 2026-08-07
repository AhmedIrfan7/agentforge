"""Links a User to an external identity provider account (roadmap step
076: Google; step 077 generalizes the code around this into a proper
provider abstraction — this table's shape doesn't need to change for
that, only the code that populates it).

A separate table rather than a google_id column on User: a user can
plausibly have more than one linked provider (Google now, GitHub or
Microsoft later per AGENTS.md's open-ecosystem goals), and "one column
per provider" doesn't scale the way "one row per linked identity" does.

Not tenant-scoped — same reasoning as models/session.py: this is about a
global identity's login methods, not anything organization-specific.
"""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OAuthIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (
        # The real invariant: this external account can only ever map to
        # one of our Users. Nothing stops one User from linking several
        # different providers (no uniqueness on user_id alone).
        UniqueConstraint(
            "provider", "provider_user_id", name="uq_oauth_identities_provider_subject"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "google" today; a plain str (not a DB enum) for the same reason
    # VerificationToken.purpose is — a new provider is an application-level
    # addition, not a migration.
    provider: Mapped[str] = mapped_column(nullable=False)
    # The provider's own stable identifier for this account (Google's
    # `sub` claim) — never the email, which a user can change.
    provider_user_id: Mapped[str] = mapped_column(nullable=False)
    # Snapshot of the email this identity had when linked — for display/
    # audit only, never used to re-derive identity (provider_user_id is).
    email: Mapped[str] = mapped_column(nullable=False)
