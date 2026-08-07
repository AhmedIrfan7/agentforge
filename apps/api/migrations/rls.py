"""Row-Level Security helpers for tenant-scoped tables' migrations.

Every table using models.mixins.TenantScopedMixin must call enable_rls()
in its creation migration's upgrade(), and disable_rls() in downgrade() —
see docs/adr/0003-multi-tenancy-isolation-strategy.md. The application
sets the session variable this policy checks via
'SET app.current_tenant_id = ...' per request (tenant-context middleware,
roadmap step 044) — until that's set, every row is denied by default,
which is the fail-closed behavior we want.

NULLIF(..., '') guards a real Postgres gotcha with pooled connections: a
custom GUC like app.current_tenant_id, once SET LOCAL at least once on a
given physical connection, reverts to '' (not NULL) once that transaction
ends — not "never set" (which is NULL). A later request reusing that
pooled connection, that queries a tenant-scoped table WITHOUT setting
app.current_tenant_id itself first (e.g. a lookup that only needs a
different permissive policy, like invitations' invitation_by_token),
still has this policy's USING clause evaluated — '' cast to ::uuid throws
InvalidTextRepresentationError instead of just failing the row match.
Found live (roadmap step 074) — the NullPool used in tests opens a fresh
connection per test, so this never surfaced there. NULLIF turns that
stale '' back into NULL first, so the cast is NULL::uuid (valid, and the
row correctly fails to match) instead of ''::uuid (invalid).
"""

from alembic import op


def enable_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    # FORCE is required too — without it, Postgres exempts the table owner
    # (the role our own application connects as) from RLS entirely.
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON {table_name}
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
    """)


def disable_rls(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
