import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Shared request shape for dense (step 120), keyword (step 121),
    and hybrid (step 122) retrieval -- identical fields for all three
    mechanisms, so this is defined once rather than duplicated
    per-mechanism, same "build inline for the first consumer,
    promote/share once a second needs the identical shape" pattern this
    pipeline has used throughout. Renamed from step 120's own
    DenseSearchRequest now that a second real consumer exists -- a
    Python class rename only, not a wire-format change (FastAPI's
    response_model controls serialization, not the JSON key names,
    which stay the same either way).

    document_id/document_type (step 123) are the two real, populated
    fields this codebase can actually filter by today -- not a
    speculative generic filter DSL. document_id scopes to one document
    (a common real RAG need); document_type comes from agents/
    document_analysis.py's own classification (step 095), already
    stored in Document.doc_metadata. Both optional, both None by
    default -- no filtering unless a caller asks for it."""

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    document_id: uuid.UUID | None = None
    document_type: str | None = None


class SearchResultRead(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    score: float
