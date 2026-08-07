"""OAuthIdentity has no tenant_id — same reasoning as repositories/user.py
and repositories/verification_token.py."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.oauth_identity import OAuthIdentity


class OAuthIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_provider_and_subject(
        self, *, provider: str, provider_user_id: str
    ) -> OAuthIdentity | None:
        result = await self.session.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == provider,
                OAuthIdentity.provider_user_id == provider_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, **fields: Any) -> OAuthIdentity:
        identity = OAuthIdentity(**fields)
        self.session.add(identity)
        await self.session.flush()
        return identity
