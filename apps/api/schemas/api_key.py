import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    key_prefix: str
    created_by_user_id: uuid.UUID
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreateResponse(ApiKeyRead):
    # The raw key -- present ONLY on this, the one response that can
    # ever carry it. Every other read of an ApiKey (ApiKeyRead) never
    # has access to it at all, not even hashed.
    key: str
