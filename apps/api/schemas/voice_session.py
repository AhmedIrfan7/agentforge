import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VoiceSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    ended_at: datetime | None
    created_at: datetime
