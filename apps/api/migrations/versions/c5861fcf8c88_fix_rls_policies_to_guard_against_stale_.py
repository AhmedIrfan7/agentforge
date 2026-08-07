"""fix RLS policies to guard against stale empty session vars

Revision ID: c5861fcf8c88
Revises: 0a09d64b88b6
Create Date: 2026-08-07 23:50:03.154166

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5861fcf8c88"
down_revision: str | Sequence[str] | None = "0a09d64b88b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table that already has enable_rls()'s tenant_isolation policy
# applied, from before this fix — see migrations/rls.py's module
# docstring for the bug this repairs.
_TENANT_ISOLATION_TABLES = ["workspaces", "memberships", "audit_logs", "invitations"]


def upgrade() -> None:
    """Upgrade schema.

    Found live testing the invitation-accept endpoint (roadmap step 074):
    get_invitation_by_token_hash() queries invitations without setting
    app.current_tenant_id (it doesn't know the tenant yet — that's the
    question the token answers), relying only on the invitation_by_token
    policy. But Postgres still evaluates every permissive policy's USING
    clause, including tenant_isolation's, and on a pooled connection
    previously used by a request that DID set app.current_tenant_id,
    that GUC reverts to '' (not NULL) once the earlier transaction ends —
    so ''::uuid throws InvalidTextRepresentationError instead of just
    failing to match. NULLIF(..., '') below turns that stale '' back into
    NULL first, so the row correctly fails to match instead of erroring.
    Same fix applied to own_memberships (app.current_user_id).
    """
    for table_name in _TENANT_ISOLATION_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table_name}
            USING (
                tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
            )
        """)

    op.execute("DROP POLICY IF EXISTS own_memberships ON memberships")
    op.execute("""
        CREATE POLICY own_memberships ON memberships
        FOR SELECT
        USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)
    """)


def downgrade() -> None:
    """Downgrade schema.

    Restores the pre-fix policy text exactly (bug and all) — this is a
    like-for-like revert, not a safety net; there's no reason to run it
    outside of testing the migration chain itself.
    """
    for table_name in _TENANT_ISOLATION_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table_name}
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        """)

    op.execute("DROP POLICY IF EXISTS own_memberships ON memberships")
    op.execute("""
        CREATE POLICY own_memberships ON memberships
        FOR SELECT
        USING (user_id = current_setting('app.current_user_id', true)::uuid)
    """)
