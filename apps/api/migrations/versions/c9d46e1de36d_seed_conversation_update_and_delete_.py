"""seed conversation update and delete permissions

Revision ID: c9d46e1de36d
Revises: 3132d06dea6d
Create Date: 2026-08-15 19:05:40.052661

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d46e1de36d"
down_revision: str | Sequence[str] | None = "3132d06dea6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same tier as conversation:create/message:create -- renaming/pinning/
# archiving/deleting YOUR OWN conversation is the same core product USE
# as starting or continuing one, not admin-tier configuration. viewer
# stays excluded (same reasoning as create/message: it never creates a
# conversation via the real endpoint in the first place, so it never
# owns one to update/delete either).
GRANTED_ROLES = [
    "org_owner",
    "admin",
    "manager",
    "knowledge_manager",
    "developer",
    "support_agent",
    "analyst",
    "end_user",
]

PERMISSIONS = [
    ("conversation:update", "Rename, pin/unpin, or archive a conversation."),
    ("conversation:delete", "Permanently delete a conversation."),
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
        "('conversation:update', 'conversation:delete'))"
    )
    op.execute(
        "DELETE FROM permissions WHERE key IN ('conversation:update', 'conversation:delete')"
    )
