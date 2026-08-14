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

As of step 133, `/context` is the polished, product-facing search
surface `SearchRequest`/`SearchResultRead`'s own docstrings already
promised: composes strategy choice (dense/keyword/hybrid), optional
multi-query expansion (search_multi_query, step 130), optional
reranking (rerank, step 125), context_builder.build_context (dedupe/
group/token-budget, step 126), and citations.build_citations (step
127) into one real HTTP response -- the first real caller of all four.
Parent-child expansion (expand_to_parent, step 131) is deliberately
NOT wired in here: it changes what a chunk's own `text` even means
(a wider window, not the original match) in a way that would need to
happen before token-budgeting, not after -- a real design question
step 133's own terse roadmap wording ("Add knowledge-base search API
endpoint") doesn't settle, so it's left out rather than guessed at.
document_info is built with a plain per-document DocumentRepository.
get() loop, not a new bulk-fetch method -- the candidate set reaching
this point is already bounded by max_tokens (typically a handful of
distinct documents), so there was nothing here to honestly justify a
new repository method with no other real caller yet, the same "add
machinery when a real need proves it" discipline used throughout this
pipeline.

As of step 134, /context is cached in Redis (redis_client.py's shared
client, already used by rate_limit.py -- celery_app.py's own comment
already anticipated this exact "cache" use case). The cache key hashes
tenant_id + knowledge_base_id + every request field (sha256 over
canonical JSON, not string concatenation, which risks ambiguous field
boundaries) -- "tenant-scoped" per this step's own roadmap wording,
so two tenants issuing the identical query text never collide. A real,
stated limitation, not silently worked around: a flat 5-minute TTL is
the only invalidation mechanism -- no hook into document reindex/
delete (steps 114/116), so a cached response can serve stale chunks
for up to five minutes after an edit; the roadmap's own line ("Add
tenant-scoped retrieval caching") doesn't ask for reindex-aware
invalidation, and building one wasn't going to be guessed at here.

Disabled under settings.environment == "test", same reasoning and same
precedent as rate_limit.py: redis_client is a module-level singleton
whose connection pool binds to whichever event loop first uses it
(same class of issue db.py's SQLAlchemy engine has under pytest) --
every test in this file would touch it for the first time via /context
now, and without per-test cleanup, connections would leak across the
many separate event loops pytest-anyio creates. Real caching behavior
is proven in its own dedicated file (tests/test_retrieval_caching.py)
with settings.environment patched to "production" and its own
disconnect-after-test fixture, exactly the isolation rate_limit.py's
own test file already established -- not duplicated here, and not
exercised by this file's ~20 existing/unrelated endpoint tests.
"""

import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agents.retriever import RetrievedChunk, RetrieverAgent
from citations import DocumentInfo, build_citations
from config import settings
from context_builder import ContextCandidate, build_context
from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from embeddings.openai import OpenAIEmbeddingProvider
from redis_client import redis_client
from repositories.chunk import ChunkRepository
from repositories.document import DocumentRepository
from rerankers.lexical import LexicalReranker
from schemas.retrieval import (
    ContextResultRead,
    ContextSearchRequest,
    SearchRequest,
    SearchResultRead,
)
from vectorstore.base import SearchFilters
from vectorstore.pgvector import PgVectorStore

_CONTEXT_CACHE_TTL_SECONDS = 300

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
_reranker = LexicalReranker()


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


def _context_cache_key(
    tenant_id: uuid.UUID, knowledge_base_id: uuid.UUID, body: ContextSearchRequest
) -> str:
    payload = {
        "tenant_id": str(tenant_id),
        "knowledge_base_id": str(knowledge_base_id),
        "query": body.query,
        "strategy": body.strategy,
        "top_k": body.top_k,
        "max_tokens": body.max_tokens,
        "rerank": body.rerank,
        "multi_query": body.multi_query,
        "document_id": str(body.document_id) if body.document_id else None,
        "document_type": body.document_type,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"retrieval_context:{digest}"


@router.post(
    "/context",
    response_model=list[ContextResultRead],
    dependencies=[Depends(require_permission("knowledge_base:read"))],
)
async def build_search_context(
    body: ContextSearchRequest,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> list[ContextResultRead]:
    cache_key = _context_cache_key(tenant_id, knowledge_base.id, body)
    if settings.environment != "test":
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return [ContextResultRead.model_validate(item) for item in json.loads(cached)]

    repo = ChunkRepository(session, tenant_id)
    filters = SearchFilters(document_id=body.document_id, document_type=body.document_type)

    async def search(query: str) -> list[RetrievedChunk]:
        if body.strategy == "dense":
            return await _retriever_agent.search_dense(
                tenant_id, knowledge_base.id, query, top_k=body.top_k, filters=filters
            )
        if body.strategy == "keyword":
            return await _retriever_agent.search_keyword(
                repo, knowledge_base.id, query, top_k=body.top_k, filters=filters
            )
        return await _retriever_agent.search_hybrid(
            tenant_id, repo, knowledge_base.id, query, top_k=body.top_k, filters=filters
        )

    if body.multi_query:
        results = await _retriever_agent.search_multi_query(body.query, search, top_k=body.top_k)
    else:
        results = await search(body.query)

    if body.rerank:
        results = await _retriever_agent.rerank(_reranker, body.query, results)

    candidates = [
        ContextCandidate(id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score)
        for r in results
    ]
    context_chunks = build_context(candidates, max_tokens=body.max_tokens)

    document_repo = DocumentRepository(session, tenant_id)
    document_info: dict[uuid.UUID, DocumentInfo] = {}
    for document_id in {c.document_id for c in context_chunks}:
        document = await document_repo.get(document_id)
        if document is None:
            raise RuntimeError(f"document {document_id} referenced by a real chunk was not found")
        document_info[document_id] = DocumentInfo(
            title=document.title, knowledge_base_name=knowledge_base.name
        )

    citations = build_citations(context_chunks, document_info=document_info)
    text_by_chunk_id = {c.id: c.text for c in context_chunks}

    results_out = [
        ContextResultRead(
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            document_title=citation.document_title,
            knowledge_base_name=citation.knowledge_base_name,
            section=citation.section,
            text=text_by_chunk_id[citation.chunk_id],
        )
        for citation in citations
    ]

    if settings.environment != "test":
        await redis_client.set(
            cache_key,
            json.dumps([r.model_dump(mode="json") for r in results_out]),
            ex=_CONTEXT_CACHE_TTL_SECONDS,
        )

    return results_out
