"""Tests for repositories/chunk.py:ChunkRepository.search_by_keyword
(roadmap step 121) -- exercises the real Postgres full-text search
against a real Chunk.search_vector (a DB-computed tsvector column,
models/chunk.py) and its real GIN index, same "no mocks for
infrastructure this project owns" reasoning test_pgvector_store.py
(step 119) already established for the sibling dense-search adapter.
"""

import uuid

import pytest

from db import get_session, set_tenant_context
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace
from repositories.chunk import ChunkRepository


async def _new_org_workspace_kb_document(slug: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Keyword Search Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="KW WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="KW KB", slug=f"{slug}-kb"
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


@pytest.mark.anyio
async def test_search_by_keyword_matches_and_ranks_relevant_chunks() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("kw-rank")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add_all(
            [
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text="Our refund policy allows returns within thirty days.",
                    start=0,
                    end=1,
                    index=0,
                ),
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text="The quick brown fox jumps over the lazy dog.",
                    start=1,
                    end=2,
                    index=1,
                ),
            ]
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)
        results = await repo.search_by_keyword(kb_id, "refund policy", top_k=10)

    assert len(results) == 1
    assert "refund policy" in results[0].text
    assert results[0].document_id == document_id


@pytest.mark.anyio
async def test_search_by_keyword_respects_top_k() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("kw-topk")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add_all(
            [
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text=f"apple banana cherry chunk number {i}",
                    start=i,
                    end=i + 1,
                    index=i,
                )
                for i in range(5)
            ]
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)
        results = await repo.search_by_keyword(kb_id, "apple banana", top_k=2)

    assert len(results) == 2


@pytest.mark.anyio
async def test_search_by_keyword_is_scoped_to_knowledge_base() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("kw-scope")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        knowledge_base = await session.get(KnowledgeBase, kb_id)
        assert knowledge_base is not None

        other_kb = KnowledgeBase(
            tenant_id=tenant_id,
            workspace_id=knowledge_base.workspace_id,
            name="Other KB",
            slug="kw-scope-other-kb",
        )
        session.add(other_kb)
        await session.flush()

        other_document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=other_kb.id,
            title="other.txt",
            storage_key="kw-scope/other.txt",
            content_type="text/plain",
            size_bytes=10,
        )
        session.add(other_document)
        await session.flush()

        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                text="widget pricing details in target kb",
                start=0,
                end=1,
                index=0,
            )
        )
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=other_document.id,
                text="widget pricing details in other kb",
                start=0,
                end=1,
                index=0,
            )
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)
        results = await repo.search_by_keyword(kb_id, "widget pricing", top_k=10)

    assert len(results) == 1
    assert "target kb" in results[0].text


@pytest.mark.anyio
async def test_search_by_keyword_with_no_matches_returns_empty_list() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("kw-nomatch")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                text="completely unrelated content here",
                start=0,
                end=1,
                index=0,
            )
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)
        results = await repo.search_by_keyword(kb_id, "refund policy", top_k=10)

    assert results == []
