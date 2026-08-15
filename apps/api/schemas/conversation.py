import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    assistant_id: uuid.UUID
    user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
