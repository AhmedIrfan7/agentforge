"""seed invitation create permission

Revision ID: 017f224e6497
Revises: 31e215fb5bfc
Create Date: 2026-08-07 20:52:34.923413

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017f224e6497"
down_revision: str | Sequence[str] | None = "31e215fb5bfc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same three roles that can create a workspace (1d0ef14faf9e) get to
# invite teammates too — the "can bring people/things into the org"
# tier, not the "can destroy the org" tier org_owner alone holds.
GRANTED_ROLES = ["org_owner", "admin", "manager"]


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    permission_id = uuid.uuid4()
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.UUID()),
        sa.column("key", sa.String()),
        sa.column("description", sa.String()),
    )
    op.bulk_insert(
        permissions_table,
        [
            {
                "id": permission_id,
                "key": "invitation:create",
                "description": "Invite a new teammate into an organization.",
            }
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
        [{"role_id": role_ids[name], "permission_id": permission_id} for name in GRANTED_ROLES],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id = "
        "(SELECT id FROM permissions WHERE key = 'invitation:create')"
    )
    op.execute("DELETE FROM permissions WHERE key = 'invitation:create'")
