import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from models.organization import Organization
from models.workspace import Workspace


@pytest.mark.anyio
async def test_create_and_read_workspace_within_tenant_context() -> None:
    # flush (not commit): RLS is still enforced per-statement, but nothing
    # persists once the session closes without committing — see
    # tests/test_tenant_isolation.py's module docstring.
    async with get_session() as session:
        org = Organization(name="Workspace Test Org", slug="workspace-test-org")
        session.add(org)
        await session.flush()

        # No tenant-context middleware yet (roadmap step 044) — set it
        # directly for this test.
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Engineering", slug="engineering")
        session.add(workspace)
        await session.flush()

        result = await session.execute(select(Workspace).where(Workspace.slug == "engineering"))
        fetched = result.scalar_one()
        assert fetched.name == "Engineering"
        assert fetched.tenant_id == org.id
