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


class ChunkingStrategyOverrideRequest(BaseModel):
    """roadmap step 103 -- strategy is plain str, not a pydantic Literal:
    validated against agents/chunking_recommendation.py:STRATEGY_NAMES
    in the router instead, so the error message can list the actual
    allowed values the same way UnsupportedFileTypeError (validation.py,
    step 085) does, rather than Literal's generic mismatch message."""

    strategy: str


class ChunkingDecisionRead(BaseModel):
    strategy: str
    source: str  # "accepted" (matches the agent's own recommendation) or "override"
    reasoning: str
