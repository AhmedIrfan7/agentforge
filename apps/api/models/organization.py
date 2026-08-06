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
