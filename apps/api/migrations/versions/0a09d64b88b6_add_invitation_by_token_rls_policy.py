"""add invitation by token RLS policy

Revision ID: 0a09d64b88b6
Revises: 017f224e6497
Create Date: 2026-08-07 23:38:33.287939

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a09d64b88b6"
down_revision: str | Sequence[str] | None = "017f224e6497"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Same dual-policy idea as 03c691d922d4's own_memberships, applied to
    accepting an invitation (step 074): the accept endpoint only has a
    raw token, not a tenant_id, so tenant_isolation alone can never
    surface the row. A second, separate PERMISSIVE policy (combined with
    tenant_isolation via OR) permits SELECT where token_hash matches the
    session variable set by db.py:set_lookup_token_hash() — scoped to
    exactly the one row the caller already proved possession of, not a
    blanket bypass. Once that lookup reveals the invitation's tenant_id,
    the caller switches to set_tenant_context() for the accept/update.
    """
    op.execute("""
        CREATE POLICY invitation_by_token ON invitations
        FOR SELECT
        USING (token_hash = current_setting('app.lookup_token_hash', true))
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS invitation_by_token ON invitations")
