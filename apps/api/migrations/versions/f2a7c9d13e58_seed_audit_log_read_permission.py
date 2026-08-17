"""seed audit log read permission

Revision ID: f2a7c9d13e58
Revises: e91a4c6f0b32
Create Date: 2026-08-17 04:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a7c9d13e58"
down_revision: str | Sequence[str] | None = "e91a4c6f0b32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# org_owner/admin only -- same tier as security_settings:* (migration
# 7f502a484e54): audit logs routinely contain permission changes and
# security events, more sensitive than day-to-day membership
# management, so manager/analyst don't get it here.
GRANTED_ROLES = ["org_owner", "admin"]

PERMISSION_KEY = "audit_log:read"
PERMISSION_DESCRIPTION = "View an organization's audit log."


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.UUID()),
        sa.column("key", sa.String()),
        sa.column("description", sa.String()),
    )
    permission_id = uuid.uuid4()
    op.bulk_insert(
        permissions_table,
        [{"id": permission_id, "key": PERMISSION_KEY, "description": PERMISSION_DESCRIPTION}],
    )

    role_ids = [
        row.id
        for row in connection.execute(
            sa.text("SELECT id FROM roles WHERE name IN :names").bindparams(
                sa.bindparam("names", expanding=True)
            ),
            {"names": GRANTED_ROLES},
        ).fetchall()
    ]

    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.UUID()),
        sa.column("permission_id", sa.UUID()),
    )
    op.bulk_insert(
        role_permissions_table,
        [{"role_id": role_id, "permission_id": permission_id} for role_id in role_ids],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        f"(SELECT id FROM permissions WHERE key = '{PERMISSION_KEY}')"
    )
    op.execute(f"DELETE FROM permissions WHERE key = '{PERMISSION_KEY}'")
