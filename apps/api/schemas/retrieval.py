import uuid
from typing import Literal

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


class ContextSearchRequest(BaseModel):
    """Request shape for the polished search endpoint (roadmap step
    133) -- deliberately its own schema, not a SearchRequest extension:
    this endpoint composes retrieval strategy choice, optional
    reranking, and optional multi-query expansion, none of which
    SearchRequest's three plumbing-proving consumers (dense/keyword/
    hybrid, steps 120-122) need or should grow just because a fourth,
    richer endpoint exists.

    strategy defaults to "hybrid" -- the strongest single mechanism
    already built (combines dense + keyword via RRF, step 122), the
    same reasonable default a caller with no strong opinion should get.
    max_tokens defaults to 2000 -- a real, stated budget for the
    context this endpoint assembles (context_builder.py, step 126),
    not unbounded; 16000 as an upper bound is a sanity ceiling against
    a pathological request, not a claim about any particular model's
    real context window (no chat/generation model is chosen yet, steps
    150+)."""

    query: str = Field(min_length=1, max_length=2000)
    strategy: Literal["dense", "keyword", "hybrid"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=50)
    max_tokens: int = Field(default=2000, ge=1, le=16000)
    rerank: bool = False
    multi_query: bool = False
    document_id: uuid.UUID | None = None
    document_type: str | None = None


class ContextResultRead(BaseModel):
    """The polished endpoint's own real output shape -- text plus real
    citation fields (citations.py, step 127), not SearchResultRead's
    minimal chunk_id/document_id/text/score. `score` is deliberately
    absent here, same reasoning citations.py:Citation already
    established for dropping it: a ranking signal from the stages
    before this one, not part of the final, citable context payload."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    knowledge_base_name: str
    section: str | None
    text: str
