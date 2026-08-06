"""A User is a global identity — one person, one row, regardless of how
many organizations they belong to. Organization/workspace/role scoping
happens through Membership (models/membership.py), not here. No auth
fields yet (password hash, etc.) — those land with Milestone 2's
authentication work; adding half-finished auth fields now would just be
dead weight until then.
"""

from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(nullable=False)

    # Platform Super Admin (AGENTS.md role matrix) operates across every
    # organization, not within one — a per-org Membership role can't
    # express that, so it's a flag here instead.
    is_platform_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
