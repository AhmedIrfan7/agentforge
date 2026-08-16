"""The Organization is the tenant root — see docs/adr/0003-multi-tenancy-isolation-strategy.md.

Organization itself has no tenant_id: it IS the tenant boundary everything
else scopes against.
"""

from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    # Branding (roadmap step 234) -- an org-level default, not yet read
    # by anything: apps/widget's own per-embed theme (step 206) is set
    # directly on the embed snippet, same honest "configuration exists,
    # no consumer wired up yet" shape SecuritySettings' own session/
    # password fields already established.
    logo_url: Mapped[str | None] = mapped_column(nullable=True)
    primary_color: Mapped[str | None] = mapped_column(nullable=True)
