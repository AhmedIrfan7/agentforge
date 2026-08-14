"""Tests for vectorstore/base.py (roadmap step 118).

Same reasoning test_embedding_provider.py already established for this
project's other interface-first step (106): step 118 is the interface
alone, with no consumer until step 119/120. This proves the narrower
thing that's actually true at this step: a real class implementing
exactly the documented Protocol shape works the way the interface
promises, not just that it type-checks.
"""

import uuid
from dataclasses import dataclass, field

import pytest

from vectorstore.base import SearchFilters, VectorRecord, VectorSearchResult, VectorStore


@dataclass
class _FakeVectorStore:
    """A real implementation of VectorStore -- not a mock of one -- same
    reasoning _FakeEmbeddingProvider (test_embedding_provider.py) and
    FakeOAuthProvider (test_google_oauth_endpoints.py) already
    established for this project's other provider interfaces."""

    name: str
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
        # Real, if trivial, similarity: score by how many leading
        # components match exactly -- enough to prove ordering/top_k
        # behavior without needing real cosine-similarity math for a
        # fake implementation.
        def _match_score(record: VectorRecord) -> float:
            pairs = zip(record.embedding, query_vector, strict=False)
            return sum(1.0 for a, b in pairs if a == b)

        candidates: list[VectorRecord] = list(self._records.values())
        # document_id filtering is real here -- VectorRecord carries it.
        # document_type isn't: VectorRecord (deliberately, see vectorstore/
        # base.py's own docstring) doesn't carry document metadata, only
        # PgVectorStore's real join-through-Document implementation can
        # honestly filter by it -- tested directly against real Postgres
        # in test_pgvector_store.py instead of faked here.
        if filters is not None and filters.document_id is not None:
            candidates = [r for r in candidates if r.document_id == filters.document_id]

        scored = [
            VectorSearchResult(
                chunk_id=record.id,
                document_id=record.document_id,
                text=record.text,
                score=_match_score(record),
            )
            for record in candidates
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]


def test_fake_store_satisfies_the_protocol_structurally() -> None:
    store: VectorStore = _FakeVectorStore(name="fake")
    assert store.name == "fake"


@pytest.mark.anyio
async def test_upsert_then_search_returns_the_matching_record() -> None:
    store = _FakeVectorStore(name="fake")
    tenant_id = uuid.uuid4()
    kb_id = uuid.uuid4()
    document_id = uuid.uuid4()
    record = VectorRecord(
        id=uuid.uuid4(), document_id=document_id, text="a real chunk of text", embedding=[1.0, 0.0]
    )

    await store.upsert(tenant_id, kb_id, [record])
    results = await store.search(tenant_id, kb_id, [1.0, 0.0], top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == record.id
    assert results[0].document_id == document_id
    assert results[0].text == "a real chunk of text"


@pytest.mark.anyio
async def test_search_respects_top_k() -> None:
    store = _FakeVectorStore(name="fake")
    tenant_id = uuid.uuid4()
    kb_id = uuid.uuid4()
    records = [
        VectorRecord(id=uuid.uuid4(), document_id=uuid.uuid4(), text=f"chunk {i}", embedding=[1.0])
        for i in range(5)
    ]

    await store.upsert(tenant_id, kb_id, records)
    results = await store.search(tenant_id, kb_id, [1.0], top_k=2)

    assert len(results) == 2


@pytest.mark.anyio
async def test_search_on_empty_store_returns_no_results() -> None:
    store = _FakeVectorStore(name="fake")
    results = await store.search(uuid.uuid4(), uuid.uuid4(), [1.0, 0.0])
    assert results == []


@pytest.mark.anyio
async def test_search_filters_by_document_id() -> None:
    store = _FakeVectorStore(name="fake")
    tenant_id = uuid.uuid4()
    kb_id = uuid.uuid4()
    target_document_id = uuid.uuid4()
    records = [
        VectorRecord(
            id=uuid.uuid4(), document_id=target_document_id, text="in target", embedding=[1.0]
        ),
        VectorRecord(id=uuid.uuid4(), document_id=uuid.uuid4(), text="in other", embedding=[1.0]),
    ]

    await store.upsert(tenant_id, kb_id, records)
    results = await store.search(
        tenant_id, kb_id, [1.0], filters=SearchFilters(document_id=target_document_id)
    )

    assert len(results) == 1
    assert results[0].text == "in target"
