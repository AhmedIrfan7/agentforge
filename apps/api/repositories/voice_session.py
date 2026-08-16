"""VoiceSessionRepository (roadmap step 220) -- thin
`TenantScopedRepository` subclass, same shape `ConversationRepository`
already established. `create()` is inherited as-is (no extra fields to
default or validate beyond what the base already does); a `get_active`
-style lookup isn't added here since nothing in this step's own scope
needs one yet -- step 228's own "voice-session-end" is the real future
caller that will need to fetch-then-update a specific session by id,
matching `repo.get(id)` the base class already provides.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models.voice_session import VoiceSession
from repositories.base import TenantScopedRepository


class VoiceSessionRepository(TenantScopedRepository[VoiceSession]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, VoiceSession)
