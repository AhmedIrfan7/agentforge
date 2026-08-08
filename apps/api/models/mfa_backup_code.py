"""One-time recovery codes for MFA (roadmap step 078) — generated once
when TOTP is confirmed, shown to the user exactly once, and consumed
one-by-one if their authenticator device is ever lost. Hashed with
argon2 (auth/passwords.py), the same as a real password: a backup code
functions exactly like a single-use password, so it deserves the same
slow, salted hash rather than a fast digest like refresh tokens use —
unlike a refresh token's 256 bits of generated entropy, a backup code is
short enough (auth/mfa.py:generate_backup_codes) that a fast hash would
leave a DB dump crackable.

Not tenant-scoped — same reasoning as models/session.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MfaBackupCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mfa_backup_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
