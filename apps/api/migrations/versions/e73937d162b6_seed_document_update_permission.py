"""seed document update permission

Revision ID: e73937d162b6
Revises: 188fb1a82a84
Create Date: 2026-08-14 11:12:01.599674

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e73937d162b6"
down_revision: str | Sequence[str] | None = "188fb1a82a84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same tier as document:create/read (b13e46412c00) -- no reason a
# document's first-ever mutation-after-creation permission should have a
# different tier than creating or reading it.
GRANTED_ROLES = ["org_owner", "admin", "manager"]

PERMISSIONS = [
    ("document:update", "Change a document's processing configuration (e.g. chunking strategy)."),
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
        "(SELECT id FROM permissions WHERE key IN ('document:update'))"
    )
    op.execute("DELETE FROM permissions WHERE key IN ('document:update')")
