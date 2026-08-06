"""Import every model module here so its table registers on db.Base.metadata
for Alembic autogenerate — see migrations/env.py."""

from models.organization import Organization
from models.workspace import Workspace

__all__ = ["Organization", "Workspace"]
