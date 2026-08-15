"""seed conversation read permission

Revision ID: 66cdd6f112e4
Revises: 2bf340555aee
Create Date: 2026-08-15 18:21:57.834578

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "66cdd6f112e4"
down_revision: str | Sequence[str] | None = "2bf340555aee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Broader than conversation:create/message:create -- viewer IS included
# here, unlike those two. Reading a conversation's own history is
# exactly what a read-only role is for; viewer just never has anything
# of its own to create in the first place. guest still gets nothing.
GRANTED_ROLES = [
    "org_owner",
    "admin",
    "manager",
    "knowledge_manager",
    "developer",
    "support_agent",
    "analyst",
    "viewer",
    "end_user",
]

PERMISSIONS = [
    ("conversation:read", "View a conversation's details or history."),
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
        "(SELECT id FROM permissions WHERE key IN ('conversation:read'))"
    )
    op.execute("DELETE FROM permissions WHERE key IN ('conversation:read')")
