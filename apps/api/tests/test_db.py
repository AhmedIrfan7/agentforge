import pytest
from sqlalchemy import text

from db import get_session


@pytest.mark.anyio
async def test_can_connect_and_run_query() -> None:
    async with get_session() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
