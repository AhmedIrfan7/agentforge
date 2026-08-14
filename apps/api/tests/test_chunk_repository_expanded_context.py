"""Tests for repositories/chunk.py:ChunkRepository.get_expanded_context
(roadmap step 131) -- exercises real Postgres, same "no mocks for
infrastructure this project owns" reasoning test_chunk_repository_
keyword_search.py (step 121) already established.
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
from repositories.chunk import ChunkRepository


async def _new_org_workspace_kb_document(slug: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Expanded Context Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="EC WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="EC KB", slug=f"{slug}-kb"
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
async def test_expanded_context_includes_neighbors_within_the_window() -> None:
    tenant_id, _kb_id, document_id = await _new_org_workspace_kb_document("ec-window")
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
                )
                for i in range(5)
            ]
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Chunk).where(
                Chunk.tenant_id == tenant_id, Chunk.document_id == document_id, Chunk.index == 2
            )
        )
        middle_chunk_id = result.scalar_one().id

        repo = ChunkRepository(session, tenant_id)
        context = await repo.get_expanded_context(middle_chunk_id, window=1)

    assert context == "chunk 1\n\nchunk 2\n\nchunk 3"


@pytest.mark.anyio
async def test_window_clamps_at_the_start_of_a_document_without_error() -> None:
    tenant_id, _kb_id, document_id = await _new_org_workspace_kb_document("ec-start")
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
                )
                for i in range(3)
            ]
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Chunk).where(
                Chunk.tenant_id == tenant_id, Chunk.document_id == document_id, Chunk.index == 0
            )
        )
        first_chunk_id = result.scalar_one().id

        repo = ChunkRepository(session, tenant_id)
        context = await repo.get_expanded_context(first_chunk_id, window=1)

    assert context == "chunk 0\n\nchunk 1"


@pytest.mark.anyio
async def test_window_zero_returns_only_the_target_chunk() -> None:
    tenant_id, _kb_id, document_id = await _new_org_workspace_kb_document("ec-zero")
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
                )
                for i in range(3)
            ]
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Chunk).where(
                Chunk.tenant_id == tenant_id, Chunk.document_id == document_id, Chunk.index == 1
            )
        )
        middle_chunk_id = result.scalar_one().id

        repo = ChunkRepository(session, tenant_id)
        context = await repo.get_expanded_context(middle_chunk_id, window=0)

    assert context == "chunk 1"


@pytest.mark.anyio
async def test_expansion_never_crosses_into_a_different_document() -> None:
    tenant_id, kb_id, document_id = await _new_org_workspace_kb_document("ec-cross-doc")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        other_document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            title="other.txt",
            storage_key="ec-cross-doc/other.txt",
            content_type="text/plain",
            size_bytes=10,
        )
        session.add(other_document)
        await session.flush()

        # Same index (0) in a different document -- must never be
        # treated as this chunk's own neighbor.
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                text="target chunk",
                start=0,
                end=1,
                index=0,
            )
        )
        session.add(
            Chunk(
                tenant_id=tenant_id,
                document_id=other_document.id,
                text="other document chunk",
                start=0,
                end=1,
                index=0,
            )
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Chunk).where(
                Chunk.tenant_id == tenant_id, Chunk.document_id == document_id, Chunk.index == 0
            )
        )
        target_chunk_id = result.scalar_one().id

        repo = ChunkRepository(session, tenant_id)
        context = await repo.get_expanded_context(target_chunk_id, window=1)

    assert context == "target chunk"


@pytest.mark.anyio
async def test_expanding_a_nonexistent_chunk_raises() -> None:
    tenant_id, _kb_id, _document_id = await _new_org_workspace_kb_document("ec-missing")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)

        with pytest.raises(ValueError, match="does not exist"):
            await repo.get_expanded_context(uuid.uuid4())
