"""Import every model module here so its table registers on db.Base.metadata
for Alembic autogenerate — see migrations/env.py."""

from models.membership import Membership
from models.organization import Organization
from models.permission import Permission, RolePermission
from models.role import Role
from models.user import User
from models.workspace import Workspace

__all__ = [
    "Membership",
    "Organization",
    "Permission",
    "Role",
    "RolePermission",
    "User",
    "Workspace",
]
