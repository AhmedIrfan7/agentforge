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
    # Real Document columns as of step 104 -- unlike extracted_text/
    # content_hash (deliberately NOT exposed here: too large, or purely
    # an internal dedup signal), the current chunking strategy is
    # genuinely useful for a client to see without a separate call, and
    # there's no dedicated GET for just the decision -- the override
    # endpoint (step 103) is PATCH-only, doubling as read+write for
    # whatever it just set, not a way to read the current state without
    # changing it.
    chunking_strategy: str | None
    chunking_strategy_source: str | None
    chunking_strategy_reasoning: str | None
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


class PipelineStageRead(BaseModel):
    stage: str
    status: str


class DocumentPipelineStatusRead(BaseModel):
    """Roadmap step 111 -- richer than DocumentStatusRead's single flat
    string: a per-stage breakdown (pipeline_status.py) plus real Chunk
    counts, for a client that wants to show ingestion progress rather
    than just poll for the final terminal status."""

    id: uuid.UUID
    status: str
    stages: list[PipelineStageRead]
    chunk_count: int
    embedded_chunk_count: int
    updated_at: datetime
