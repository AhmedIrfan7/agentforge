"""Retrieval endpoints -- dense (vector similarity, step 120) and
keyword/full-text (Postgres tsvector, step 121). Deliberately two
separate endpoints, not two modes of one: confirmed at step 118's own
design that VectorStore is vector-similarity only, and keyword search
is a genuinely different mechanism (Chunk.search_vector, a DB-computed
tsvector column, models/chunk.py) with its own index type (GIN vs
ivfflat) and its own query shape (@@ match + ts_rank, not cosine
distance) -- not something that belongs behind the same abstraction.
Step 122 ("hybrid retrieval combining dense+keyword") is where these
two get combined into one call; until then they stay two real,
independently useful, independently testable endpoints.

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
gap as steps 107/108/111-114/117) -- a real dense_search request fails
closed with a plain 500 (errors.py's generic handler), the honest shape
for a genuine backend-dependency failure, not a client-facing 4xx.
keyword_search has no such dependency and works for real in every
environment, including this one.
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
from schemas.retrieval import SearchRequest, SearchResultRead
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
    results = await _vector_store.search(
        tenant_id, knowledge_base.id, query_vectors[0], top_k=body.top_k
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
    results = await repo.search_by_keyword(knowledge_base.id, body.query, top_k=body.top_k)
    return [
        SearchResultRead(chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score)
        for r in results
    ]
