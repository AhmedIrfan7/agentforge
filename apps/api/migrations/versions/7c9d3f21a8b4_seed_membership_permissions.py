"""seed membership permissions

Revision ID: 7c9d3f21a8b4
Revises: 331109d18ff0
Create Date: 2026-08-17 09:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c9d3f21a8b4"
down_revision: str | Sequence[str] | None = "331109d18ff0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same tier as invitation:create/read/revoke -- inviting is how members
# get ADDED, this is how their existing role gets managed/removed; no
# reason the access tier should differ between the two halves of "who's
# in this org."
GRANTED_ROLES = ["org_owner", "admin", "manager"]

PERMISSIONS = [
    ("membership:read", "List an organization's members and their roles."),
    ("membership:update", "Change an existing member's role."),
    ("membership:delete", "Remove a member from an organization."),
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
        [
            {"role_id": role_id, "permission_id": permission_id}
            for permission_id in permission_ids.values()
            for role_id in role_ids
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    keys = [key for key, _description in PERMISSIONS]
    keys_sql = ", ".join(f"'{key}'" for key in keys)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN "
        f"(SELECT id FROM permissions WHERE key IN ({keys_sql}))"
    )
    op.execute(f"DELETE FROM permissions WHERE key IN ({keys_sql})")
