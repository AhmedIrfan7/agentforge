"""Row-Level Security helpers for tenant-scoped tables' migrations.

Every table using models.mixins.TenantScopedMixin must call enable_rls()
in its creation migration's upgrade(), and disable_rls() in downgrade() —
see docs/adr/0003-multi-tenancy-isolation-strategy.md. The application
sets the session variable this policy checks via
'SET app.current_tenant_id = ...' per request (tenant-context middleware,
roadmap step 044) — until that's set, every row is denied by default,
which is the fail-closed behavior we want.
"""

from alembic import op


def enable_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    # FORCE is required too — without it, Postgres exempts the table owner
    # (the role our own application connects as) from RLS entirely.
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON {table_name}
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    """)


def disable_rls(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
