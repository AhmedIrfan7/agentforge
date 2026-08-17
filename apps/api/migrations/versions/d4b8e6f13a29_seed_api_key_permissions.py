"""seed api_key permissions

Revision ID: d4b8e6f13a29
Revises: a3f7d92c5e1b
Create Date: 2026-08-17 06:05:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4b8e6f13a29"
down_revision: str | Sequence[str] | None = "a3f7d92c5e1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same tier as membership:*/invitation:* -- managing an org's own
# standing credentials is the same "org_owner/admin/manager" class of
# administrative action as managing who's in the org.
GRANTED_ROLES = ["org_owner", "admin", "manager"]

PERMISSIONS = [
    ("api_key:create", "Generate a new API key for the organization."),
    ("api_key:read", "List an organization's API keys (name/prefix/creator, never the secret)."),
    ("api_key:delete", "Revoke an API key."),
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
