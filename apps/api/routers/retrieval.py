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

dense_search is the first real caller of vectorstore/pgvector.py:
PgVectorStore.search() and embeddings/openai.py:OpenAIEmbeddingProvider
.embed() (steps 107/119). A free-text query has to become a vector
before PgVectorStore.search() can run anything -- this endpoint's own
real job, beyond wiring, is that one extra step: embed the query with
the SAME provider that embedded the chunks, since comparing vectors
from two different embedding models/dimensions would be meaningless.
Own module-level _embedding_provider singleton, same shape
embeddings_pipeline.py's own module-level instance already uses, rather
than reaching into that other module's underscore-prefixed (module-
private) attribute -- there's exactly one real EmbeddingProvider in
this codebase (checked at step 107), so a second lightweight instance
costs nothing and keeps this module's own tests independent.

keyword_search calls repositories/chunk.py:ChunkRepository.
search_by_keyword directly -- no provider, no embedding step, a
free-text query becomes a Postgres tsquery synchronously in the same
request, genuinely simpler than dense search's own extra async
round trip.

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
here as everywhere numbers get surfaced in this codebase. Each
underlying retriever is queried for HYBRID_CANDIDATE_POOL_SIZE results
regardless of the caller's own requested top_k, then fused and
truncated -- fusing only within each retriever's own top_k (if a caller
asked for a small one) risks missing a chunk that ranks well in one
retriever but just outside the other's narrow top_k, defeating the
point of combining two signals.

As of step 123, SearchRequest.document_id/document_type (schemas/
retrieval.py) are passed through to all three endpoints -- dense via
vectorstore/base.py:SearchFilters, keyword/hybrid's own keyword-search
half via ChunkRepository.search_by_keyword's own keyword arguments.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from embeddings.base import EmbeddingProvider
from embeddings.openai import OpenAIEmbeddingProvider
from repositories.chunk import ChunkRepository
from retrieval_fusion import reciprocal_rank_fusion
from schemas.retrieval import SearchRequest, SearchResultRead
from vectorstore.base import SearchFilters
from vectorstore.pgvector import PgVectorStore

HYBRID_CANDIDATE_POOL_SIZE = 50

router = APIRouter(
    prefix=(
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}"
    ),
    tags=["retrieval"],
)

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]

_embedding_provider: EmbeddingProvider = OpenAIEmbeddingProvider()
_vector_store = PgVectorStore()


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
    query_vectors = await _embedding_provider.embed([body.query])
    filters = SearchFilters(document_id=body.document_id, document_type=body.document_type)
    results = await _vector_store.search(
        tenant_id, knowledge_base.id, query_vectors[0], top_k=body.top_k, filters=filters
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
    results = await repo.search_by_keyword(
        knowledge_base.id,
        body.query,
        top_k=body.top_k,
        document_id=body.document_id,
        document_type=body.document_type,
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
    query_vectors = await _embedding_provider.embed([body.query])
    filters = SearchFilters(document_id=body.document_id, document_type=body.document_type)
    dense_results = await _vector_store.search(
        tenant_id,
        knowledge_base.id,
        query_vectors[0],
        top_k=HYBRID_CANDIDATE_POOL_SIZE,
        filters=filters,
    )

    repo = ChunkRepository(session, tenant_id)
    keyword_results = await repo.search_by_keyword(
        knowledge_base.id,
        body.query,
        top_k=HYBRID_CANDIDATE_POOL_SIZE,
        document_id=body.document_id,
        document_type=body.document_type,
    )

    fused_scores = reciprocal_rank_fusion(
        [[r.chunk_id for r in dense_results], [r.chunk_id for r in keyword_results]]
    )
    # (document_id, text) only -- not the whole result object, since
    # dense/keyword results are two unrelated dataclasses that happen to
    # share field names, not a common type mypy can unify across a
    # combined iterable.
    lookup: dict[uuid.UUID, tuple[uuid.UUID, str]] = {
        r.chunk_id: (r.document_id, r.text) for r in dense_results
    }
    lookup.update({r.chunk_id: (r.document_id, r.text) for r in keyword_results})
    ranked_ids = sorted(fused_scores, key=lambda chunk_id: fused_scores[chunk_id], reverse=True)

    return [
        SearchResultRead(
            chunk_id=chunk_id,
            document_id=lookup[chunk_id][0],
            text=lookup[chunk_id][1],
            score=fused_scores[chunk_id],
        )
        for chunk_id in ranked_ids[: body.top_k]
    ]
