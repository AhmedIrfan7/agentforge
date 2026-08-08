"""MfaBackupCode has no tenant_id — same reasoning as repositories/user.py
and repositories/verification_token.py."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.mfa_backup_code import MfaBackupCode


class MfaBackupCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_many(self, *, user_id: uuid.UUID, hashes: list[str]) -> None:
        for code_hash in hashes:
            self.session.add(MfaBackupCode(user_id=user_id, code_hash=code_hash))
        await self.session.flush()

    async def list_unused(self, user_id: uuid.UUID) -> Sequence[MfaBackupCode]:
        result = await self.session.execute(
            select(MfaBackupCode).where(
                MfaBackupCode.user_id == user_id, MfaBackupCode.used_at.is_(None)
            )
        )
        return result.scalars().all()

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.session.execute(delete(MfaBackupCode).where(MfaBackupCode.user_id == user_id))
