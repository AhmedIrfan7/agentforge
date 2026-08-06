"""One shared token table for every "prove you own this email" flow —
verify-email (step 065), magic-link login (step 066), and password
reset (step 067) all need the identical shape (generate opaque token,
email it, verify it once, expire it) — three near-identical tables
would just be duplication, not a real distinction. `purpose` keeps
tokens for one flow from being usable in another (a magic-link token
must not also work as a password-reset token).

Not tenant-scoped — same reasoning as models/session.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class VerificationToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    # "email_verify" | "magic_link" | "password_reset" — plain str, not a
    # DB enum: a fourth purpose later is an application-level addition,
    # not a migration.
    purpose: Mapped[str] = mapped_column(nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
