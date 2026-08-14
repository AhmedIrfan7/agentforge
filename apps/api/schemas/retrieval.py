import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Shared request shape for dense (step 120) and keyword (step 121)
    retrieval -- identical fields for both mechanisms, so this is
    defined once rather than duplicated per-mechanism, same "build
    inline for the first consumer, promote/share once a second needs
    the identical shape" pattern this pipeline has used throughout.
    Renamed from step 120's own DenseSearchRequest now that a second
    real consumer exists -- a Python class rename only, not a wire-
    format change (FastAPI's response_model controls serialization, not
    the JSON key names, which stay the same either way)."""

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)


class SearchResultRead(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    score: float
