"""seed document permissions

Revision ID: b13e46412c00
Revises: f3a9fe0bb607
Create Date: 2026-08-09 00:17:24.806854

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b13e46412c00"
down_revision: str | Sequence[str] | None = "f3a9fe0bb607"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same tier as knowledge_base:create/read/delete (7b7d9996ea30) -- a
# document is a knowledge-base-level resource, no reason for its access
# tier to differ from knowledge_base's own.
GRANTED_ROLES = ["org_owner", "admin", "manager"]

PERMISSIONS = [
    ("document:create", "Upload a document into a knowledge base."),
    ("document:read", "View a document's details."),
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
        "(SELECT id FROM permissions WHERE key IN ('document:create', 'document:read'))"
    )
    op.execute("DELETE FROM permissions WHERE key IN ('document:create', 'document:read')")
