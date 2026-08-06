import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
