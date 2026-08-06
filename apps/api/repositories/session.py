"""Session isn't tenant-scoped (models/session.py), so this doesn't fit
TenantScopedRepository either."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.session import Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_refresh_token_hash(self, token_hash: str) -> Session | None:
        result = await self.session.execute(
            select(Session).where(Session.refresh_token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        device_info: str | None = None,
        ip_address: str | None = None,
    ) -> Session:
        session = Session(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            last_active_at=datetime.now(expires_at.tzinfo),
            device_info=device_info,
            ip_address=ip_address,
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def revoke(self, session: Session) -> None:
        session.revoked_at = datetime.now(session.expires_at.tzinfo)
        await self.session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Password reset (step 067) calls this: if the account was
        compromised, any already-logged-in session could be the
        attacker's — a reset should invalidate all of them, not just
        change the password going forward."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        )
        for existing in result.scalars().all():
            existing.revoked_at = now
        await self.session.flush()
