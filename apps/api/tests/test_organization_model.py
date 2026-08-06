import pytest
from sqlalchemy import select

from db import get_session
from models.organization import Organization


@pytest.mark.anyio
async def test_create_and_read_organization() -> None:
    # flush (not commit) + the session's implicit rollback-on-close leaves
    # no trace in the database regardless of pass/fail — see
    # tests/test_tenant_isolation.py's module docstring for why this
    # matters more than usual in a suite with RLS-scoped session state.
    async with get_session() as session:
        org = Organization(name="Acme Corp", slug="acme-corp-test")
        session.add(org)
        await session.flush()

        result = await session.execute(
            select(Organization).where(Organization.slug == "acme-corp-test")
        )
        fetched = result.scalar_one()
        assert fetched.name == "Acme Corp"
        assert fetched.id == org.id
