"""A User is a global identity — one person, one row, regardless of how
many organizations they belong to. Organization/workspace/role scoping
happens through Membership (models/membership.py), not here.
"""

from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(nullable=False)

    # Nullable: a user who signs up via Google OAuth (roadmap step 076)
    # will never have one. Never store or compare plaintext — see
    # auth/passwords.py.
    hashed_password: Mapped[str | None] = mapped_column(nullable=True)

    is_email_verified: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Platform Super Admin (AGENTS.md role matrix) operates across every
    # organization, not within one — a per-org Membership role can't
    # express that, so it's a flag here instead.
    is_platform_admin: Mapped[bool] = mapped_column(default=False, nullable=False)

    # MFA/TOTP (roadmap step 078). mfa_totp_secret_encrypted holding a
    # value while mfa_enabled is still False means "enrollment started but
    # never confirmed" — deliberately not a separate status column; those
    # two fields alone already distinguish never-enrolled (both empty),
    # pending (secret set, not enabled) and active (both set) without
    # anything that could drift out of sync. Encrypted, not hashed — see
    # auth/mfa.py: a TOTP secret must be recoverable in plaintext to
    # verify a code against it, unlike a password.
    mfa_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    mfa_totp_secret_encrypted: Mapped[str | None] = mapped_column(nullable=True)
