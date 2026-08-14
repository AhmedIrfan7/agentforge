"""seed document delete permission

Revision ID: 1d331e8f214b
Revises: 9c8d8867b814
Create Date: 2026-08-14 18:00:35.202002

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d331e8f214b"
down_revision: str | Sequence[str] | None = "9c8d8867b814"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same tier as document:create/read/update (b13e46412c00, e73937d162b6)
# and knowledge_base:delete (7b7d9996ea30) -- deleting a document is a
# more destructive action than updating one, but this project has never
# split a resource's delete tier away from its own create/read/update
# tier (knowledge_base:delete sits at the same org_owner/admin/manager
# tier as knowledge_base:create/read too), so there's no established
# precedent for treating document:delete any differently.
GRANTED_ROLES = ["org_owner", "admin", "manager"]

PERMISSIONS = [
    ("document:delete", "Delete a document and its version/chunk history."),
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
        "(SELECT id FROM permissions WHERE key IN ('document:delete'))"
    )
    op.execute("DELETE FROM permissions WHERE key IN ('document:delete')")
