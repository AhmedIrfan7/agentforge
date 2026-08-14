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
"""

import uuid
from dataclasses import dataclass

from agents.base import Agent
from embeddings.base import EmbeddingProvider
from repositories.chunk import ChunkRepository
from rerankers.base import RerankCandidate, RerankerProvider
from retrieval_fusion import reciprocal_rank_fusion
from vectorstore.base import SearchFilters, VectorStore

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
        query_vectors = await self._embedding_provider.embed([query])
        results = await self._vector_store.search(
            tenant_id, knowledge_base_id, query_vectors[0], top_k=top_k, filters=filters
        )
        return [
            RetrievedChunk(
                chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score
            )
            for r in results
        ]

    async def search_keyword(
        self,
        chunk_repo: ChunkRepository,
        knowledge_base_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        results = await chunk_repo.search_by_keyword(
            knowledge_base_id,
            query,
            top_k=top_k,
            document_id=filters.document_id if filters else None,
            document_type=filters.document_type if filters else None,
        )
        return [
            RetrievedChunk(
                chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score
            )
            for r in results
        ]

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
        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=lookup[chunk_id].document_id,
                text=lookup[chunk_id].text,
                score=fused_scores[chunk_id],
            )
            for chunk_id in ranked_ids[:top_k]
        ]

    async def rerank(
        self, reranker: RerankerProvider, query: str, results: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        candidates = [RerankCandidate(id=r.chunk_id, text=r.text) for r in results]
        rerank_results = await reranker.rerank(query, candidates)

        lookup = {r.chunk_id: r for r in results}
        return [
            RetrievedChunk(
                chunk_id=rr.id,
                document_id=lookup[rr.id].document_id,
                text=lookup[rr.id].text,
                score=rr.score,
            )
            for rr in rerank_results
        ]
