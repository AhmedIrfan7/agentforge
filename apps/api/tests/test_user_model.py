import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db import get_session
from models.user import User


@pytest.mark.anyio
async def test_create_and_read_user() -> None:
    async with get_session() as session:
        user = User(email="ada@example.com", full_name="Ada Lovelace")
        session.add(user)
        await session.flush()

        result = await session.execute(select(User).where(User.email == "ada@example.com"))
        fetched = result.scalar_one()
        assert fetched.full_name == "Ada Lovelace"
        assert fetched.is_platform_admin is False


@pytest.mark.anyio
async def test_email_must_be_unique() -> None:
    async with get_session() as session:
        session.add(User(email="dup@example.com", full_name="First"))
        await session.flush()

        session.add(User(email="dup@example.com", full_name="Second"))
        with pytest.raises(IntegrityError, match="unique"):
            await session.flush()
