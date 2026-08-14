"""Per-agent unit tests with mocked providers (roadmap step 156,
AGENTS.md's own "AGENT TESTING" section: "Every agent should have...
Unit tests... Mock providers.").

RetrieverAgent (agents/retriever.py) is the one agent in this codebase
that depends on a provider-shaped external collaborator beyond a
fakeable Protocol: `ChunkRepository` (repositories/chunk.py). Unlike
`EmbeddingProvider`/`VectorStore` (both structural Protocols, already
given real fakes in test_retriever_agent.py -- this project's
established "real, tested fake over a mock" preference), `ChunkRepository`
is a concrete, SQLAlchemy-backed class with no interface seam to fake
against, so `unittest.mock.AsyncMock(spec=ChunkRepository)` is the
honest tool here -- a deliberate, narrow exception to the usual
preference, not a stylistic drift.

These are ADDITIVE to test_retriever_agent.py's existing real-Postgres
tests for search_keyword/search_hybrid/expand_to_parent, not a
replacement -- that file's own docstring already gives a real,
considered reason to keep testing ChunkRepository.search_by_keyword's
own full-text-search correctness against a real tsvector column ("no
mocks for infrastructure this project owns"). What's missing, and what
these tests add, is isolated coverage of RetrieverAgent's OWN glue
logic (result mapping, structured logging, hybrid fusion, delegation)
independent of whether Postgres's real ranking behavior happens to
agree -- exactly AGENTS.md's "Unit tests" vs. "Integration tests" as
two separate, complementary things, not one substituting for the
other. expand_to_parent is the clearest case: it's pure delegation
(`return await chunk_repo.get_expanded_context(...)`) with no logic of
its own, so a mock that asserts the exact call made IS the correct
level of test -- test_retriever_agent.py's own existing DB-backed test
for it already says as much in its own docstring.
"""

import uuid
from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest
import structlog.testing

from agents.retriever import RetrievedChunk, RetrieverAgent
from repositories.chunk import ChunkRepository, KeywordSearchResult
from vectorstore.base import SearchFilters, VectorRecord, VectorSearchResult

# Same fakes test_retriever_agent.py already defines for search_dense --
# duplicated locally rather than imported from that test module, matching
# this project's own convention of only cross-importing from
# tests/helpers.py, never test-module-to-test-module.


@dataclass
class _FakeEmbeddingProvider:
    name: str = "fake"
    dimensions: int = 2

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


@dataclass
class _FakeVectorStore:
    name: str = "fake"
    _records: dict[uuid.UUID, VectorRecord] = field(default_factory=dict)

    async def upsert(
        self, tenant_id: uuid.UUID, knowledge_base_id: uuid.UUID, records: list[VectorRecord]
    ) -> None:
        for record in records:
            self._records[record.id] = record

    async def search(
        self,
        tenant_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        query_vector: list[float],
        *,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[VectorSearchResult]:
        candidates = list(self._records.values())
        if filters is not None and filters.document_id is not None:
            candidates = [r for r in candidates if r.document_id == filters.document_id]
        return [
            VectorSearchResult(chunk_id=r.id, document_id=r.document_id, text=r.text, score=1.0)
            for r in candidates[:top_k]
        ]


def _mock_chunk_repository() -> AsyncMock:
    return AsyncMock(spec=ChunkRepository)


@pytest.mark.anyio
async def test_search_keyword_maps_results_and_logs_using_a_mocked_repository() -> None:
    kb_id = uuid.uuid4()
    document_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    repo = _mock_chunk_repository()
    repo.search_by_keyword.return_value = [
        KeywordSearchResult(
            chunk_id=chunk_id, document_id=document_id, text="refund policy", score=0.8
        )
    ]

    agent = RetrieverAgent(_FakeEmbeddingProvider(), _FakeVectorStore())
    with structlog.testing.capture_logs() as logs:
        results = await agent.search_keyword(repo, kb_id, "refund policy", top_k=5)

    assert results == [
        RetrievedChunk(chunk_id=chunk_id, document_id=document_id, text="refund policy", score=0.8)
    ]
    repo.search_by_keyword.assert_awaited_once_with(
        kb_id, "refund policy", top_k=5, document_id=None, document_type=None
    )
    events = [e for e in logs if e["event"] == "retrieval_keyword_search"]
    assert len(events) == 1
    assert events[0]["result_count"] == 1


@pytest.mark.anyio
async def test_search_hybrid_fuses_a_mocked_keyword_result_with_a_fake_dense_result() -> None:
    tenant_id = uuid.uuid4()
    kb_id = uuid.uuid4()
    dense_document_id = uuid.uuid4()
    keyword_document_id = uuid.uuid4()
    dense_chunk_id = uuid.uuid4()
    keyword_chunk_id = uuid.uuid4()

    vector_store = _FakeVectorStore()
    await vector_store.upsert(
        tenant_id,
        kb_id,
        [
            VectorRecord(
                id=dense_chunk_id,
                document_id=dense_document_id,
                text="dense hit",
                embedding=[1.0, 0.0],
            )
        ],
    )

    repo = _mock_chunk_repository()
    repo.search_by_keyword.return_value = [
        KeywordSearchResult(
            chunk_id=keyword_chunk_id,
            document_id=keyword_document_id,
            text="keyword hit",
            score=0.5,
        )
    ]

    agent = RetrieverAgent(_FakeEmbeddingProvider(), vector_store)
    results = await agent.search_hybrid(tenant_id, repo, kb_id, "query", top_k=10)

    result_ids = {r.chunk_id for r in results}
    assert result_ids == {dense_chunk_id, keyword_chunk_id}
    repo.search_by_keyword.assert_awaited_once()


@pytest.mark.anyio
async def test_expand_to_parent_delegates_to_a_mocked_repository() -> None:
    chunk_id = uuid.uuid4()
    repo = _mock_chunk_repository()
    repo.get_expanded_context.return_value = "first chunk\n\nsecond chunk\n\nthird chunk"

    agent = RetrieverAgent(_FakeEmbeddingProvider(), _FakeVectorStore())
    result = await agent.expand_to_parent(repo, chunk_id, window=2)

    assert result == "first chunk\n\nsecond chunk\n\nthird chunk"
    repo.get_expanded_context.assert_awaited_once_with(chunk_id, window=2)
