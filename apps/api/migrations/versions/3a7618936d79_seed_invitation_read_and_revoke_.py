"""seed invitation read and revoke permissions

Revision ID: 3a7618936d79
Revises: c5861fcf8c88
Create Date: 2026-08-07 23:58:11.128079

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a7618936d79"
down_revision: str | Sequence[str] | None = "c5861fcf8c88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same three roles as invitation:create (017f224e6497) — seeing and
# revoking invites is part of the same "manage who's being brought into
# the org" tier, not a separate concern.
GRANTED_ROLES = ["org_owner", "admin", "manager"]

PERMISSIONS = [
    ("invitation:read", "View an organization's pending/past invitations."),
    ("invitation:revoke", "Revoke a pending invitation before it's accepted."),
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
        "(SELECT id FROM permissions WHERE key IN ('invitation:read', 'invitation:revoke'))"
    )
    op.execute("DELETE FROM permissions WHERE key IN ('invitation:read', 'invitation:revoke')")
