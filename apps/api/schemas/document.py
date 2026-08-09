import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    title: str
    status: str
    doc_metadata: dict[str, object]
    content_type: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime


class DocumentStatusRead(BaseModel):
    """Deliberately smaller than DocumentRead (roadmap step 088) -- a
    client polling for upload/processing progress doesn't need title,
    doc_metadata, content_type, etc. re-sent on every poll tick, only
    whether status has changed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    updated_at: datetime
