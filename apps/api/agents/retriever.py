"""Retriever Agent (roadmap step 124, AGENTS.md SECTION 5) -- wraps the
three real retrieval mechanisms (dense/keyword/hybrid, steps 120-123)
behind one agent-shaped interface, matching AGENTS.md's own Agent
Registry vision for this codebase. Unlike document_analysis.py/
chunking_recommendation.py (both pure, synchronous, single-input
functions over already-in-memory text), this is the first agent that
talks to real collaborators -- an EmbeddingProvider, a VectorStore, a
DB-session-scoped ChunkRepository -- so its methods are async and take
those collaborators rather than raw text. name still exists purely for
AGENTS.md's "independent logging" tag (base.py), same as every other
agent; nothing here forces a shared run() shape across agents that
still don't need one (base.py's own stated reasoning from step 097).

This is a genuine "extract, don't rewrite" step: search_dense/
search_keyword/search_hybrid are the exact logic that previously lived
inline in routers/retrieval.py's three endpoint functions (dense_
search/keyword_search/hybrid_search), moved here unchanged so the
router becomes thin wiring (request in, agent call, schema out) --
same "build inline for first consumer, promote once a second/real
reason exists" pattern this project used for get_target_knowledge_base
(step 120) and SearchRequest/SearchResultRead (step 121), except here
the promotion reason is AGENTS.md's own Agent Registry design, not a
second call site.

RetrievedChunk is this agent's own return shape (chunk_id/document_id/
text/score), not schemas.retrieval.SearchResultRead -- no module under
agents/, repositories/, or vectorstore/ imports from schemas/ anywhere
in this codebase (checked before writing this file); schemas/ is a
router-facing (FastAPI response_model) layer, and this agent has no
business depending on it. It's also not VectorSearchResult or
KeywordSearchResult: hybrid's fused result has neither dataclass's
exact provenance, and giving all three methods one common return type
is what lets routers/retrieval.py's endpoints share one identical
"map to SearchResultRead" list comprehension instead of three
near-identical ones.

ChunkRepository is passed in per-call, not held on the agent, because
it's constructed from a request-scoped AsyncSession (routers/
retrieval.py already builds ChunkRepository(session, tenant_id) fresh
per request) -- an agent instance is built once at module import time
(same module-level singleton shape routers/retrieval.py already used
for _embedding_provider/_vector_store before this step), so it can't
hold a collaborator whose lifetime is one request.

As of step 125, `rerank()` adds reranking as its own separate,
explicit stage -- AGENTS.md's own "Design reranking as an independent
stage" taken literally: it is NOT folded into search_dense/
search_keyword/search_hybrid (each already produces its own real
ranking), so calling it is opt-in, on results a caller already has.
`reranker: RerankerProvider` is a per-call parameter, not a
constructor-held collaborator like embedding_provider/vector_store --
there's no router step yet that always wants reranking applied (unlike
embedding_provider/vector_store, which every dense/hybrid call needs),
so nothing yet justifies a fixed, always-used instance.

As of step 129, every search_*/rerank method logs one structured event
(query, result count, scores, latency_ms) via `logging_config.py`'s
existing `get_logger(__name__)` convention (module-level `logger`,
snake_case event name as the first positional arg -- same shape
errors.py/main.py/notifications/email.py already use). Query text is
logged verbatim, not hashed or redacted -- this codebase has no
existing PII-redaction convention for logged user input (notifications/
email.py already logs a real recipient email address the same way),
so redacting only retrieval queries would be a new, inconsistent
policy invented here rather than an established one applied
consistently; `_log_retrieval` is one small private helper shared by
all three search_* methods (identical shape each time), not
duplicated three times, since `rerank()`'s own event has a genuinely
different field set (no `knowledge_base_id`, no query embedding step)
and stays separate.

As of step 130, `search_multi_query()` adds multi-query retrieval:
expands a query into variants (multi_query.py:expand_query, a real
deterministic heuristic, not an LLM call -- no chat/generation step
exists yet, see multi_query.py's own docstring), runs a caller-
supplied single-query search closure once per variant, and fuses the
per-variant result lists with the same reciprocal_rank_fusion already
trusted by search_hybrid. `search: Callable[[str], Awaitable[list[
RetrievedChunk]]]` is a query-only closure, the same "caller binds its
own mechanism-specific collaborators before passing a plain closure
in" pattern eval/harness.py already established at step 128 --
multi-query retrieval is an orthogonal axis to WHICH mechanism runs
(dense, keyword, or even hybrid), so this method has no business
picking one itself; a caller passes e.g. `lambda q: agent.search_dense
(tenant_id, kb_id, q, top_k=N)`.

As of step 131, `expand_to_parent()` adds parent-child chunk retrieval
-- another separate, opt-in stage (same "independent stage" shape as
`rerank()`), not folded into search_dense/search_keyword/search_hybrid:
forcing every search result to fetch its expanded context would be a
real behavior/performance change nobody asked for. Thin wrapper over
`repositories/chunk.py:ChunkRepository.get_expanded_context()`, which
owns the real "chunk window expansion" logic (see its own docstring
for why this reconstructs a parent context from existing chunk
neighbors rather than needing a new stored-parent-chunk schema).
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from agents.base import Agent
from embeddings.base import EmbeddingProvider
from logging_config import get_logger
from multi_query import expand_query
from repositories.chunk import ChunkRepository
from rerankers.base import RerankCandidate, RerankerProvider
from retrieval_fusion import reciprocal_rank_fusion
from vectorstore.base import SearchFilters, VectorStore

logger = get_logger(__name__)

# Same reasoning and same value as routers/retrieval.py's own pre-step-124
# constant: each underlying retriever is queried for this many candidates
# regardless of the caller's requested top_k, then fused and truncated --
# fusing only within each retriever's own (possibly small) top_k risks
# missing a chunk that ranks well in one retriever but just outside the
# other's narrow top_k.
HYBRID_CANDIDATE_POOL_SIZE = 50


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    score: float


def _log_retrieval(
    event: str,
    *,
    query: str,
    knowledge_base_id: uuid.UUID,
    results: list[RetrievedChunk],
    latency_ms: float,
) -> None:
    logger.info(
        event,
        query=query,
        knowledge_base_id=str(knowledge_base_id),
        result_count=len(results),
        scores=[r.score for r in results],
        latency_ms=round(latency_ms, 2),
    )


class RetrieverAgent(Agent):
    name = "retriever"

    def __init__(self, embedding_provider: EmbeddingProvider, vector_store: VectorStore) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def search_dense(
        self,
        tenant_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        start = time.perf_counter()
        query_vectors = await self._embedding_provider.embed([query])
        results = await self._vector_store.search(
            tenant_id, knowledge_base_id, query_vectors[0], top_k=top_k, filters=filters
        )
        mapped = [
            RetrievedChunk(
                chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score
            )
            for r in results
        ]
        _log_retrieval(
            "retrieval_dense_search",
            query=query,
            knowledge_base_id=knowledge_base_id,
            results=mapped,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        return mapped

    async def search_keyword(
        self,
        chunk_repo: ChunkRepository,
        knowledge_base_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        start = time.perf_counter()
        results = await chunk_repo.search_by_keyword(
            knowledge_base_id,
            query,
            top_k=top_k,
            document_id=filters.document_id if filters else None,
            document_type=filters.document_type if filters else None,
        )
        mapped = [
            RetrievedChunk(
                chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score
            )
            for r in results
        ]
        _log_retrieval(
            "retrieval_keyword_search",
            query=query,
            knowledge_base_id=knowledge_base_id,
            results=mapped,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        return mapped

    async def search_hybrid(
        self,
        tenant_id: uuid.UUID,
        chunk_repo: ChunkRepository,
        knowledge_base_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        start = time.perf_counter()
        dense_results = await self.search_dense(
            tenant_id,
            knowledge_base_id,
            query,
            top_k=HYBRID_CANDIDATE_POOL_SIZE,
            filters=filters,
        )
        keyword_results = await self.search_keyword(
            chunk_repo,
            knowledge_base_id,
            query,
            top_k=HYBRID_CANDIDATE_POOL_SIZE,
            filters=filters,
        )

        fused_scores = reciprocal_rank_fusion(
            [[r.chunk_id for r in dense_results], [r.chunk_id for r in keyword_results]]
        )
        # Same "dict per list, then .update(), not a combined iterable"
        # shape as routers/retrieval.py's own pre-step-124 hybrid_search --
        # both are lists of the same RetrievedChunk type here (unlike the
        # router's original two heterogeneous dataclasses), so this is now
        # just a straightforward last-write-wins merge, not a mypy
        # workaround.
        lookup: dict[uuid.UUID, RetrievedChunk] = {r.chunk_id: r for r in dense_results}
        lookup.update({r.chunk_id: r for r in keyword_results})

        ranked_ids = sorted(fused_scores, key=lambda chunk_id: fused_scores[chunk_id], reverse=True)
        mapped = [
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=lookup[chunk_id].document_id,
                text=lookup[chunk_id].text,
                score=fused_scores[chunk_id],
            )
            for chunk_id in ranked_ids[:top_k]
        ]
        # Latency covers the whole hybrid operation -- both sub-searches
        # (each already logged their own event above) plus fusion --
        # the honest end-to-end cost of calling search_hybrid, not just
        # the fusion step on its own.
        _log_retrieval(
            "retrieval_hybrid_search",
            query=query,
            knowledge_base_id=knowledge_base_id,
            results=mapped,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        return mapped

    async def rerank(
        self, reranker: RerankerProvider, query: str, results: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        start = time.perf_counter()
        candidates = [RerankCandidate(id=r.chunk_id, text=r.text) for r in results]
        rerank_results = await reranker.rerank(query, candidates)

        lookup = {r.chunk_id: r for r in results}
        reranked = [
            RetrievedChunk(
                chunk_id=rr.id,
                document_id=lookup[rr.id].document_id,
                text=lookup[rr.id].text,
                score=rr.score,
            )
            for rr in rerank_results
        ]
        logger.info(
            "retrieval_rerank",
            query=query,
            reranker=reranker.name,
            result_count=len(reranked),
            scores=[r.score for r in reranked],
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return reranked

    async def search_multi_query(
        self,
        query: str,
        search: Callable[[str], Awaitable[list[RetrievedChunk]]],
        *,
        top_k: int = 10,
    ) -> list[RetrievedChunk]:
        start = time.perf_counter()
        variants = expand_query(query)
        variant_results = [await search(variant) for variant in variants]

        fused_scores = reciprocal_rank_fusion(
            [[r.chunk_id for r in results] for results in variant_results]
        )
        lookup: dict[uuid.UUID, RetrievedChunk] = {}
        for results in variant_results:
            lookup.update({r.chunk_id: r for r in results})

        ranked_ids = sorted(fused_scores, key=lambda chunk_id: fused_scores[chunk_id], reverse=True)
        mapped = [
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=lookup[chunk_id].document_id,
                text=lookup[chunk_id].text,
                score=fused_scores[chunk_id],
            )
            for chunk_id in ranked_ids[:top_k]
        ]
        logger.info(
            "retrieval_multi_query_search",
            query=query,
            variant_count=len(variants),
            result_count=len(mapped),
            scores=[r.score for r in mapped],
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return mapped

    async def expand_to_parent(
        self, chunk_repo: ChunkRepository, chunk_id: uuid.UUID, *, window: int = 1
    ) -> str:
        return await chunk_repo.get_expanded_context(chunk_id, window=window)
