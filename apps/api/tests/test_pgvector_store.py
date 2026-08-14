"""Tests for vectorstore/pgvector.py (roadmap step 119) -- exercises
PgVectorStore directly against real Postgres and its real
ix_chunks_embedding_ivfflat index (same "no mocks for infrastructure
this project owns" reasoning test_chunk_model.py/test_embeddings_
pipeline.py already established) -- a fake vector store would prove
nothing about whether the real `<=>` cosine-distance query actually
works.
"""

import uuid

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace
from vectorstore.base import SearchFilters, VectorRecord
from vectorstore.pgvector import PgVectorStore


async def _new_org_workspace_kb_document(slug: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="PgVectorStore Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="PgVS WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="PgVS KB", slug=f"{slug}-kb"
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


def _vector(*, lead: float) -> list[float]:
    """A real 1536-dim vector, distinguishable by its first component --
    enough to prove real cosine-distance ordering without needing
    semantically meaningful embeddings."""
    return [lead] + [0.01] * 1535


@pytest.mark.anyio
async def test_search_ranks_the_closest_chunk_first() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("pgvs-rank")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add_all(
            [
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text="far chunk",
                    start=0,
                    end=1,
                    index=0,
                    embedding=_vector(lead=-1.0),
                ),
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text="near chunk",
                    start=1,
                    end=2,
                    index=1,
                    embedding=_vector(lead=0.9),
                ),
            ]
        )
        await session.commit()

    store = PgVectorStore()
    results = await store.search(tenant_id, kb_id, _vector(lead=1.0), top_k=10)

    assert len(results) == 2
    assert results[0].text == "near chunk"
    assert results[1].text == "far chunk"
    assert results[0].score > results[1].score


@pytest.mark.anyio
async def test_search_respects_top_k() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("pgvs-topk")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add_all(
            [
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text=f"chunk {i}",
                    start=i,
                    end=i + 1,
                    index=i,
                    embedding=_vector(lead=float(i)),
                )
                for i in range(5)
            ]
        )
        await session.commit()

    store = PgVectorStore()
    results = await store.search(tenant_id, kb_id, _vector(lead=0.0), top_k=2)

    assert len(results) == 2


@pytest.mark.anyio
async def test_search_is_scoped_to_knowledge_base() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("pgvs-scope")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = await session.get(Document, document_id)
        assert document is not None
        knowledge_base = await session.get(KnowledgeBase, document.knowledge_base_id)
        assert knowledge_base is not None

        other_kb = KnowledgeBase(
            tenant_id=tenant_id,
            workspace_id=knowledge_base.workspace_id,
            name="Other KB",
            slug="pgvs-scope-other-kb",
        )
        session.add(other_kb)
        await session.flush()

        other_document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=other_kb.id,
            title="other.txt",
            storage_key="pgvs-scope/other.txt",
            content_type="text/plain",
            size_bytes=10,
        )
        session.add(other_document)
        await session.flush()

        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                text="in target kb",
                start=0,
                end=1,
                index=0,
                embedding=_vector(lead=1.0),
            )
        )
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=other_document.id,
                text="in other kb",
                start=0,
                end=1,
                index=0,
                embedding=_vector(lead=1.0),
            )
        )
        await session.commit()

    store = PgVectorStore()
    results = await store.search(tenant_id, kb_id, _vector(lead=1.0), top_k=10)

    assert [r.text for r in results] == ["in target kb"]


@pytest.mark.anyio
async def test_search_excludes_chunks_without_embeddings_yet() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("pgvs-noembed")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                text="not embedded yet",
                start=0,
                end=1,
                index=0,
                embedding=None,
            )
        )
        await session.commit()

    store = PgVectorStore()
    results = await store.search(tenant_id, kb_id, _vector(lead=1.0), top_k=10)

    assert results == []


@pytest.mark.anyio
async def test_upsert_updates_an_existing_chunks_text_and_embedding() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("pgvs-upsert")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        chunk = Chunk(
            tenant_id=tenant_id,
            document_id=document_id,
            text="original text",
            start=0,
            end=1,
            index=0,
            embedding=_vector(lead=0.0),
        )
        session.add(chunk)
        await session.commit()
        chunk_id = chunk.id

    store = PgVectorStore()
    await store.upsert(
        tenant_id,
        kb_id,
        [
            VectorRecord(
                id=chunk_id,
                document_id=document_id,
                text="updated text",
                embedding=_vector(lead=5.0),
            )
        ],
    )

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Chunk).where(Chunk.id == chunk_id))
        updated = result.scalar_one()
        assert updated.text == "updated text"
        assert updated.embedding is not None
        assert updated.embedding[0] == pytest.approx(5.0)


@pytest.mark.anyio
async def test_search_filters_by_document_id() -> None:
    """Roadmap step 123."""
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("pgvs-filter-docid")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        other_document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            title="other.txt",
            storage_key="pgvs-filter-docid/other.txt",
            content_type="text/plain",
            size_bytes=10,
        )
        session.add(other_document)
        await session.flush()

        session.add_all(
            [
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text="in target document",
                    start=0,
                    end=1,
                    index=0,
                    embedding=_vector(lead=1.0),
                ),
                Chunk(
                    tenant_id=tenant_id,
                    document_id=other_document.id,
                    text="in other document",
                    start=0,
                    end=1,
                    index=0,
                    embedding=_vector(lead=1.0),
                ),
            ]
        )
        await session.commit()

    store = PgVectorStore()
    results = await store.search(
        tenant_id,
        kb_id,
        _vector(lead=1.0),
        top_k=10,
        filters=SearchFilters(document_id=document_id),
    )

    assert [r.text for r in results] == ["in target document"]


@pytest.mark.anyio
async def test_search_filters_by_document_type() -> None:
    """Roadmap step 123 -- Document.doc_metadata["document_type"] is set
    by agents/document_analysis.py (step 095) during real extraction;
    set directly here since this test doesn't run a live worker."""
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("pgvs-filter-doctype")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = await session.get(Document, document_id)
        assert document is not None
        document.doc_metadata = {"document_type": "faq"}

        other_document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            title="other.txt",
            storage_key="pgvs-filter-doctype/other.txt",
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
                    text="faq chunk",
                    start=0,
                    end=1,
                    index=0,
                    embedding=_vector(lead=1.0),
                ),
                Chunk(
                    tenant_id=tenant_id,
                    document_id=other_document.id,
                    text="manual chunk",
                    start=0,
                    end=1,
                    index=0,
                    embedding=_vector(lead=1.0),
                ),
            ]
        )
        await session.commit()

    store = PgVectorStore()
    results = await store.search(
        tenant_id, kb_id, _vector(lead=1.0), top_k=10, filters=SearchFilters(document_type="faq")
    )

    assert [r.text for r in results] == ["faq chunk"]


@pytest.mark.anyio
async def test_upsert_raises_for_a_chunk_id_that_does_not_exist() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("pgvs-upsert-missing")
    store = PgVectorStore()

    with pytest.raises(ValueError, match="cannot create chunk"):
        await store.upsert(
            tenant_id,
            kb_id,
            [
                VectorRecord(
                    id=uuid.uuid4(),
                    document_id=document_id,
                    text="text",
                    embedding=_vector(lead=1.0),
                )
            ],
        )
