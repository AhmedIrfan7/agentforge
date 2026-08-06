"""add own-membership RLS policy for cross-tenant org listing

Revision ID: 03c691d922d4
Revises: 1d0ef14faf9e
Create Date: 2026-08-06 22:36:07.132050

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "03c691d922d4"
down_revision: str | Sequence[str] | None = "1d0ef14faf9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    A second, separate PERMISSIVE policy on memberships, alongside (not
    replacing) tenant_isolation from step 043. Postgres combines multiple
    permissive policies with OR, so a row is visible if EITHER the
    session's tenant_id matches (normal tenant-scoped access) OR the
    session's user_id matches (this user's own membership, regardless of
    which tenant it's in) — needed for "list every organization I belong
    to," which can't be answered with a single tenant_id in scope. See
    db.py:set_user_context().
    """
    op.execute("""
        CREATE POLICY own_memberships ON memberships
        FOR SELECT
        USING (user_id = current_setting('app.current_user_id', true)::uuid)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS own_memberships ON memberships")
