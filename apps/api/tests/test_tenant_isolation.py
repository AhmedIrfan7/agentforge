"""Proves models/mixins.py:TenantScopedMixin + migrations/rls.py actually
block cross-tenant access, per docs/adr/0003-multi-tenancy-isolation-strategy.md.
Not a mock — this hits the real Postgres RLS policy.

Every test here uses flush(), never commit(): RLS is enforced per-statement
regardless of whether the surrounding transaction eventually commits, and
get_session()'s implicit rollback-on-close (AsyncSession.close() rolls back
an uncommitted transaction) means no test leaves data behind for the next
one to collide with — no manual cleanup needed, and SET LOCAL's
"only lasts until commit" scoping stops being a concern since these tests
never commit.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from db import get_session, set_tenant_context
from models.organization import Organization
from models.workspace import Workspace


@pytest.mark.anyio
async def test_tenant_cannot_read_another_tenants_workspace() -> None:
    async with get_session() as session:
        org_a = Organization(name="Tenant A", slug="tenant-a-isolation-test")
        org_b = Organization(name="Tenant B", slug="tenant-b-isolation-test")
        session.add_all([org_a, org_b])
        await session.flush()

        await set_tenant_context(session, org_a.id)
        workspace_a = Workspace(tenant_id=org_a.id, name="A's Workspace", slug="a-workspace")
        session.add(workspace_a)
        await session.flush()

        # Same query, different tenant context — must see nothing.
        await set_tenant_context(session, org_b.id)
        result = await session.execute(select(Workspace).where(Workspace.slug == "a-workspace"))
        assert result.scalar_one_or_none() is None

        # Confirm it's really visible again under the right tenant, so the
        # assertion above is actually testing isolation and not a broken query.
        await set_tenant_context(session, org_a.id)
        result = await session.execute(select(Workspace).where(Workspace.slug == "a-workspace"))
        assert result.scalar_one_or_none() is not None


@pytest.mark.anyio
async def test_tenant_cannot_write_row_claiming_another_tenants_id() -> None:
    async with get_session() as session:
        org_a = Organization(name="Tenant A2", slug="tenant-a2-isolation-test")
        org_b = Organization(name="Tenant B2", slug="tenant-b2-isolation-test")
        session.add_all([org_a, org_b])
        await session.flush()

        # Session claims to be tenant B, but tries to insert a row
        # tagged as tenant A — the RLS WITH CHECK clause must reject it.
        await set_tenant_context(session, org_b.id)
        malicious = Workspace(tenant_id=org_a.id, name="Spoofed", slug="spoofed-workspace")
        session.add(malicious)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.flush()
