"""Retrieval endpoints -- dense (vector similarity, step 120), keyword/
full-text (Postgres tsvector, step 121), and hybrid (step 122).
Deliberately three separate endpoints, not modes of one: confirmed at
step 118's own design that VectorStore is vector-similarity only, and
keyword search is a genuinely different mechanism (Chunk.search_vector,
a DB-computed tsvector column, models/chunk.py) with its own index type
(GIN vs ivfflat) and its own query shape (@@ match + ts_rank, not
cosine distance) -- not something that belongs behind the same
abstraction. hybrid_search calls both real retrievers and fuses their
results (retrieval_fusion.py) rather than being a third, independent
mechanism -- dense and keyword stay the two real building blocks, this
is what combines them.

As of step 124, all three endpoints are thin wiring only (request in,
agents.retriever.RetrieverAgent call, schema out) -- the actual
embed-then-search / keyword-search / fuse-two-retrievers logic lives on
RetrieverAgent now, not here (see agents/retriever.py's own docstring
for why: AGENTS.md's Agent Registry vision, and no module outside
routers/ should import schemas/). _retriever_agent is a module-level
singleton for the same reason _embedding_provider/_vector_store were
before this step -- there's exactly one real EmbeddingProvider and one
real VectorStore in this codebase (checked at steps 107/119), so
constructing the agent once at import time costs nothing.

Both share schemas.retrieval.SearchRequest/SearchResultRead (query/
top_k in, chunk_id/document_id/text/score out) -- deliberately minimal,
not enriched with a document title or metadata; this is the plumbing-
proving milestone, not the polished, product-facing search surface
(step 133 owns that once reranking/context-building/citations, steps
125-127, exist to justify a richer shape). Both reuse knowledge_base:
read, not a new permission -- searching within a knowledge base is a
read action on that resource, same "same capability, smaller/different
view" reasoning steps 088/111 already established for document:read.

No real OPENAI_API_KEY exists in this environment (the same documented
gap as steps 107/108/111-114/117) -- a real dense_search (or
hybrid_search, which needs the same embedding step) request fails
closed with a plain 500 (errors.py's generic handler), the honest shape
for a genuine backend-dependency failure, not a client-facing 4xx.
keyword_search has no such dependency and works for real in every
environment, including this one.

hybrid_search's score is a fused RRF score (retrieval_fusion.py), not a
similarity or a rank score in the sense dense/keyword's own results
are -- an intentional, documented departure from SearchResultRead's
score meaning elsewhere, the same "the algorithm's own real output
shape, not massaged to look like something it isn't" reasoning applies
here as everywhere numbers get surfaced in this codebase.

As of step 123, SearchRequest.document_id/document_type (schemas/
retrieval.py) are passed through to all three endpoints via
vectorstore/base.py:SearchFilters, which RetrieverAgent now owns
unpacking for the keyword half too.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agents.retriever import RetrieverAgent
from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from embeddings.openai import OpenAIEmbeddingProvider
from repositories.chunk import ChunkRepository
from schemas.retrieval import SearchRequest, SearchResultRead
from vectorstore.base import SearchFilters
from vectorstore.pgvector import PgVectorStore

router = APIRouter(
    prefix=(
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}"
    ),
    tags=["retrieval"],
)

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]

_retriever_agent = RetrieverAgent(OpenAIEmbeddingProvider(), PgVectorStore())


@router.post(
    "/search",
    response_model=list[SearchResultRead],
    dependencies=[Depends(require_permission("knowledge_base:read"))],
)
async def dense_search(
    body: SearchRequest,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> list[SearchResultRead]:
    filters = SearchFilters(document_id=body.document_id, document_type=body.document_type)
    results = await _retriever_agent.search_dense(
        tenant_id, knowledge_base.id, body.query, top_k=body.top_k, filters=filters
    )
    return [
        SearchResultRead(chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score)
        for r in results
    ]


@router.post(
    "/search/keyword",
    response_model=list[SearchResultRead],
    dependencies=[Depends(require_permission("knowledge_base:read"))],
)
async def keyword_search(
    body: SearchRequest,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> list[SearchResultRead]:
    repo = ChunkRepository(session, tenant_id)
    filters = SearchFilters(document_id=body.document_id, document_type=body.document_type)
    results = await _retriever_agent.search_keyword(
        repo, knowledge_base.id, body.query, top_k=body.top_k, filters=filters
    )
    return [
        SearchResultRead(chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score)
        for r in results
    ]


@router.post(
    "/search/hybrid",
    response_model=list[SearchResultRead],
    dependencies=[Depends(require_permission("knowledge_base:read"))],
)
async def hybrid_search(
    body: SearchRequest,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> list[SearchResultRead]:
    repo = ChunkRepository(session, tenant_id)
    filters = SearchFilters(document_id=body.document_id, document_type=body.document_type)
    results = await _retriever_agent.search_hybrid(
        tenant_id, repo, knowledge_base.id, body.query, top_k=body.top_k, filters=filters
    )
    return [
        SearchResultRead(chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score)
        for r in results
    ]
