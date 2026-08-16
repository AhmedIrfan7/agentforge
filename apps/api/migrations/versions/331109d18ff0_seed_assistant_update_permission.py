"""seed assistant update permission

Revision ID: 331109d18ff0
Revises: f66418ba49dc
Create Date: 2026-08-16 21:22:45.393588

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "331109d18ff0"
down_revision: str | Sequence[str] | None = "f66418ba49dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same tier as assistant:create/read/delete (8491040d82dc) -- the
# assistant-builder UI (step 238) is what finally gives this resource a
# real update endpoint; no reason its own access tier should differ
# from the other three operations on the same resource.
GRANTED_ROLES = ["org_owner", "admin", "manager"]

PERMISSION_KEY = "assistant:update"
PERMISSION_DESCRIPTION = "Edit an assistant's name/instructions/knowledge access/agent config."


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
