import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: uuid.UUID
    extra: dict[str, Any] | None
    created_at: datetime


class AuditLogListRead(BaseModel):
    items: list[AuditLogRead]
    total: int
