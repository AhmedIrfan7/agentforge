"""seed security settings permissions

Revision ID: 7f502a484e54
Revises: c02f16e313e1
Create Date: 2026-08-08 19:28:45.401844

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f502a484e54"
down_revision: str | Sequence[str] | None = "c02f16e313e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tighter than invitation:*/workspace:* (org_owner/admin/manager) --
# security posture is more sensitive than day-to-day membership
# management, so manager doesn't get it here.
GRANTED_ROLES = ["org_owner", "admin"]

PERMISSIONS = [
    ("security_settings:read", "View an organization's security settings."),
    ("security_settings:update", "Change an organization's security settings."),
]


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.UUID()),
        sa.column("key", sa.String()),
        sa.column("description", sa.String()),
    )
    permission_ids = {key: uuid.uuid4() for key, _description in PERMISSIONS}
    op.bulk_insert(
        permissions_table,
        [
            {"id": permission_ids[key], "key": key, "description": description}
            for key, description in PERMISSIONS
        ],
    )

    role_ids = {
        row.name: row.id
        for row in connection.execute(
            sa.text("SELECT id, name FROM roles WHERE name IN :names").bindparams(
                sa.bindparam("names", expanding=True)
            ),
            {"names": GRANTED_ROLES},
        ).fetchall()
    }

    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.UUID()),
        sa.column("permission_id", sa.UUID()),
    )
    op.bulk_insert(
        role_permissions_table,
        [
            {"role_id": role_ids[role_name], "permission_id": permission_ids[key]}
            for role_name in GRANTED_ROLES
            for key, _description in PERMISSIONS
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE key IN "
        "('security_settings:read', 'security_settings:update'))"
    )
    op.execute(
        "DELETE FROM permissions WHERE key IN "
        "('security_settings:read', 'security_settings:update')"
    )
