"""seed analytics read permission

Revision ID: b6e1f4a087cd
Revises: d4b8e6f13a29
Create Date: 2026-08-17 07:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6e1f4a087cd"
down_revision: str | Sequence[str] | None = "d4b8e6f13a29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# org_owner/admin/manager -- same administrative tier membership:*/
# invitation:*/api_key:* already use -- PLUS analyst, whose own seeded
# role description (migrations/versions/a870af57e4d3) already says
# "Views analytics and reports; no configuration access." verbatim --
# this is the first real permission that description has ever had
# anything to grant.
GRANTED_ROLES = ["org_owner", "admin", "manager", "analyst"]

PERMISSION_KEY = "analytics:read"
PERMISSION_DESCRIPTION = "View aggregate analytics (conversation/knowledge/agent/usage metrics)."


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
