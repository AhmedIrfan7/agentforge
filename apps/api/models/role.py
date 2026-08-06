"""Built-in role catalog — global, not tenant-scoped. AGENTS.md's role
matrix lists Platform Super Admin too, but that's User.is_platform_admin
(operates across every org, doesn't fit a per-org Membership role).

Custom per-org roles (AGENTS.md: "Support future custom roles") are
deliberately NOT modeled yet — adding a speculative nullable tenant_id
column now, before anything creates a custom role, would be exactly the
kind of premature complexity AGENTS.md also warns against. When that
feature is actually built, it's a migration adding a nullable tenant_id
+ an adjusted RLS policy, not a rewrite of this table.
"""

from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
