import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.verification_token import VerificationToken


class VerificationTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, purpose: str, expires_at: datetime
    ) -> VerificationToken:
        token = VerificationToken(
            user_id=user_id, token_hash=token_hash, purpose=purpose, expires_at=expires_at
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_valid(self, *, token_hash: str, purpose: str) -> VerificationToken | None:
        """Returns the token only if it matches the hash AND purpose —
        deliberately not just "get by hash" — a magic-link token must not
        verify as a password-reset token even if someone tries."""
        result = await self.session.execute(
            select(VerificationToken).where(
                VerificationToken.token_hash == token_hash,
                VerificationToken.purpose == purpose,
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token: VerificationToken) -> None:
        token.used_at = datetime.now(token.expires_at.tzinfo)
        await self.session.flush()
