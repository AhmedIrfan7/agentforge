"""User has no tenant_id — it's a global identity (models/user.py) — so
this doesn't fit TenantScopedRepository, same reasoning as
repositories/organization.py.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> User | None:
        return await self.session.get(User, id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, **fields: Any) -> User:
        user = User(**fields)
        self.session.add(user)
        await self.session.flush()
        return user
