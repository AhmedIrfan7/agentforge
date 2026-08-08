"""seed knowledge base permissions

Revision ID: 7b7d9996ea30
Revises: 7870d1e5dfcf
Create Date: 2026-08-08 23:26:33.010141

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b7d9996ea30"
down_revision: str | Sequence[str] | None = "7870d1e5dfcf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same tier as workspace:create/read/delete (1d0ef14faf9e) -- a
# knowledge base is a workspace-level resource, no reason for its access
# tier to differ from workspace's own.
GRANTED_ROLES = ["org_owner", "admin", "manager"]

PERMISSIONS = [
    ("knowledge_base:create", "Create a knowledge base within a workspace."),
    ("knowledge_base:read", "View a knowledge base's details."),
    ("knowledge_base:delete", "Delete a knowledge base."),
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
        "('knowledge_base:create', 'knowledge_base:read', 'knowledge_base:delete'))"
    )
    op.execute(
        "DELETE FROM permissions WHERE key IN "
        "('knowledge_base:create', 'knowledge_base:read', 'knowledge_base:delete')"
    )
