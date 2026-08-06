import pytest
from sqlalchemy import select

from db import get_session
from models.organization import Organization


@pytest.mark.anyio
async def test_create_and_read_organization() -> None:
    async with get_session() as session:
        org = Organization(name="Acme Corp", slug="acme-corp-test")
        session.add(org)
        await session.commit()

        result = await session.execute(
            select(Organization).where(Organization.slug == "acme-corp-test")
        )
        fetched = result.scalar_one()
        assert fetched.name == "Acme Corp"
        assert fetched.id == org.id

        await session.delete(fetched)
        await session.commit()
