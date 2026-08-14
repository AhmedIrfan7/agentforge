"""Tests for agents/retriever.py (roadmap step 124).

search_dense is tested against fakes (same "prove the interface
contract" reasoning test_vectorstore_base.py/test_embedding_provider.py
already established) -- it only ever calls EmbeddingProvider.embed and
VectorStore.search, both structural Protocols, so a fake proves the
agent's own wiring without needing real Postgres.

search_keyword/search_hybrid are tested against real Postgres instead
(same "no mocks for infrastructure this project owns" reasoning
test_chunk_repository_keyword_search.py/test_pgvector_store.py already
established) -- ChunkRepository.search_by_keyword is a real repository
over a real tsvector column, not something behind a fakeable Protocol.
search_hybrid additionally exercises real fusion (retrieval_fusion.py)
over one real dense result (via a fake VectorStore/EmbeddingProvider,
same as search_dense's own tests) and one real keyword result (via
real Postgres) at once -- proving the two real halves this project
already trusts independently combine correctly through the agent, not
re-proving either half's own internal correctness again.
"""

import uuid
from dataclasses import dataclass, field

import pytest

from agents.retriever import RetrieverAgent
from db import get_session, set_tenant_context
from embeddings.base import EmbeddingProvider
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace
from repositories.chunk import ChunkRepository
from vectorstore.base import SearchFilters, VectorRecord, VectorSearchResult, VectorStore


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


async def _new_org_workspace_kb_document(slug: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Retriever Agent Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Retr WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Retr KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        document = Document(
            tenant_id=org.id,
            knowledge_base_id=knowledge_base.id,
            title="doc.txt",
            storage_key=f"{slug}/doc.txt",
            content_type="text/plain",
            size_bytes=10,
        )
        session.add(document)
        await session.flush()
        await session.commit()
        return org.id, knowledge_base.id, document.id


def test_agent_satisfies_the_base_agent_shape() -> None:
    embedding_provider: EmbeddingProvider = _FakeEmbeddingProvider()
    vector_store: VectorStore = _FakeVectorStore()
    agent = RetrieverAgent(embedding_provider, vector_store)
    assert agent.name == "retriever"


@pytest.mark.anyio
async def test_search_dense_embeds_the_query_and_returns_vector_store_results() -> None:
    tenant_id, kb_id, document_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    vector_store = _FakeVectorStore()
    await vector_store.upsert(
        tenant_id,
        kb_id,
        [
            VectorRecord(
                id=uuid.uuid4(), document_id=document_id, text="a chunk", embedding=[1.0, 0.0]
            )
        ],
    )
    agent = RetrieverAgent(_FakeEmbeddingProvider(), vector_store)

    results = await agent.search_dense(tenant_id, kb_id, "some query", top_k=5)

    assert len(results) == 1
    assert results[0].text == "a chunk"
    assert results[0].document_id == document_id


@pytest.mark.anyio
async def test_search_dense_passes_filters_through_to_the_vector_store() -> None:
    tenant_id, kb_id = uuid.uuid4(), uuid.uuid4()
    target_document_id = uuid.uuid4()
    vector_store = _FakeVectorStore()
    await vector_store.upsert(
        tenant_id,
        kb_id,
        [
            VectorRecord(
                id=uuid.uuid4(),
                document_id=target_document_id,
                text="in target",
                embedding=[1.0, 0.0],
            ),
            VectorRecord(
                id=uuid.uuid4(), document_id=uuid.uuid4(), text="in other", embedding=[1.0, 0.0]
            ),
        ],
    )
    agent = RetrieverAgent(_FakeEmbeddingProvider(), vector_store)

    results = await agent.search_dense(
        tenant_id, kb_id, "query", filters=SearchFilters(document_id=target_document_id)
    )

    assert [r.text for r in results] == ["in target"]


@pytest.mark.anyio
async def test_search_keyword_matches_real_postgres_full_text_search() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("retr-agent-kw")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                text="Our refund policy allows returns within thirty days.",
                start=0,
                end=1,
                index=0,
            )
        )
        await session.commit()

    agent = RetrieverAgent(_FakeEmbeddingProvider(), _FakeVectorStore())
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)
        results = await agent.search_keyword(repo, kb_id, "refund policy", top_k=10)

    assert len(results) == 1
    assert "refund policy" in results[0].text


@pytest.mark.anyio
async def test_search_keyword_filters_by_document_type() -> None:
    """Roadmap step 123's filter, proven reachable through the agent."""
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("retr-agent-kw-filter")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = await session.get(Document, document_id)
        assert document is not None
        document.doc_metadata = {"document_type": "faq"}

        other_document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            title="other.txt",
            storage_key="retr-agent-kw-filter/other.txt",
            content_type="text/plain",
            size_bytes=10,
            doc_metadata={"document_type": "manual"},
        )
        session.add(other_document)
        await session.flush()

        session.add_all(
            [
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text="refund policy in faq",
                    start=0,
                    end=1,
                    index=0,
                ),
                Chunk(
                    tenant_id=tenant_id,
                    document_id=other_document.id,
                    text="refund policy in manual",
                    start=0,
                    end=1,
                    index=0,
                ),
            ]
        )
        await session.commit()

    agent = RetrieverAgent(_FakeEmbeddingProvider(), _FakeVectorStore())
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)
        results = await agent.search_keyword(
            repo, kb_id, "refund policy", filters=SearchFilters(document_type="faq")
        )

    assert [r.text for r in results] == ["refund policy in faq"]


@pytest.mark.anyio
async def test_search_hybrid_fuses_real_dense_and_real_keyword_results() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("retr-agent-hybrid")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                text="found by keyword search only",
                start=0,
                end=1,
                index=0,
            )
        )
        await session.commit()

    vector_store = _FakeVectorStore()
    dense_only_chunk_id = uuid.uuid4()
    await vector_store.upsert(
        tenant_id,
        kb_id,
        [
            VectorRecord(
                id=dense_only_chunk_id,
                document_id=document_id,
                text="found by dense search only",
                embedding=[1.0, 0.0],
            )
        ],
    )
    agent = RetrieverAgent(_FakeEmbeddingProvider(), vector_store)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)
        results = await agent.search_hybrid(tenant_id, repo, kb_id, "keyword search", top_k=10)

    result_texts = {r.text for r in results}
    assert result_texts == {"found by keyword search only", "found by dense search only"}
