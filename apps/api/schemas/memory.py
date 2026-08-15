import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope: str
    memory_type: str
    content: str
    importance_score: float
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
