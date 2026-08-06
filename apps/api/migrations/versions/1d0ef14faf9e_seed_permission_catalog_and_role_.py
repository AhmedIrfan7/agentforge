"""seed permission catalog and role permission matrix

Revision ID: 1d0ef14faf9e
Revises: 69d534969a1c
Create Date: 2026-08-06 22:32:08.552203

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d0ef14faf9e"
down_revision: str | Sequence[str] | None = "69d534969a1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Only permissions actually enforced by a route today (routers/organization.py,
# routers/workspace.py) — no speculative entries for endpoints that don't
# exist yet, same discipline step 041 applied to leaving this table empty
# until there was something real to put in it.
PERMISSIONS = [
    ("organization:read", "View an organization's details."),
    ("organization:update", "Edit an organization's name/settings."),
    ("organization:delete", "Delete an organization."),
    ("workspace:create", "Create a workspace within an organization."),
    ("workspace:read", "View a workspace's details."),
    ("workspace:delete", "Delete a workspace."),
]

# role_name -> permission keys. org_owner is the only role that can delete
# the organization itself (common SaaS convention — even admins usually
# can't destroy the whole account). guest gets nothing yet — "Limited,
# temporary access" (AGENTS.md role matrix) with no concrete permission
# needed until there's a resource guests specifically interact with.
ROLE_PERMISSIONS = {
    "org_owner": [
        "organization:read",
        "organization:update",
        "organization:delete",
        "workspace:create",
        "workspace:read",
        "workspace:delete",
    ],
    "admin": [
        "organization:read",
        "organization:update",
        "workspace:create",
        "workspace:read",
        "workspace:delete",
    ],
    "manager": ["organization:read", "workspace:create", "workspace:read", "workspace:delete"],
    "knowledge_manager": ["organization:read", "workspace:read"],
    "developer": ["organization:read", "workspace:read"],
    "support_agent": ["organization:read", "workspace:read"],
    "analyst": ["organization:read", "workspace:read"],
    "viewer": ["organization:read", "workspace:read"],
    "end_user": ["workspace:read"],
    "guest": [],
}


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
        for row in connection.execute(sa.text("SELECT id, name FROM roles")).fetchall()
    }

    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.UUID()),
        sa.column("permission_id", sa.UUID()),
    )
    rows = [
        {"role_id": role_ids[role_name], "permission_id": permission_ids[permission_key]}
        for role_name, permission_keys in ROLE_PERMISSIONS.items()
        for permission_key in permission_keys
    ]
    if rows:
        op.bulk_insert(role_permissions_table, rows)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM role_permissions")
    op.execute("DELETE FROM permissions")
