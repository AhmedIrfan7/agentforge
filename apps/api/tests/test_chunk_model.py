"""Model-only test (roadmap step 105) -- no dispatcher creates a Chunk
yet (see models/chunk.py's docstring for the real, tracked gap between
this step and 108). Same pattern as test_document_model.py: exercises
the ORM/RLS layer directly, since there's no router to go through.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db import get_session, set_tenant_context
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace


async def _new_org_workspace_kb_document(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Chunk Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Chunk WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Chunk KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        document = Document(
            tenant_id=org.id,
            knowledge_base_id=knowledge_base.id,
            title="doc.txt",
            storage_key=f"{slug}/doc.txt",
            content_type="text/plain",
            size_bytes=100,
            extracted_text="First chunk text. Second chunk text.",
        )
        session.add(document)
        await session.flush()
        await session.commit()
        return org.id, document.id


@pytest.mark.anyio
async def test_create_and_read_chunk_within_tenant_context() -> None:
    tenant_id, document_id = await _new_org_workspace_kb_document("chunk-create")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        chunk = Chunk(
            tenant_id=tenant_id,
            document_id=document_id,
            text="First chunk text.",
            start=0,
            end=17,
            index=0,
        )
        session.add(chunk)
        await session.flush()

        result = await session.execute(select(Chunk).where(Chunk.document_id == document_id))
        fetched = result.scalar_one()
        assert fetched.tenant_id == tenant_id
        assert fetched.text == "First chunk text."
        assert fetched.start == 0
        assert fetched.end == 17
        assert fetched.index == 0


@pytest.mark.anyio
async def test_multiple_chunks_for_one_document_keep_their_order() -> None:
    tenant_id, document_id = await _new_org_workspace_kb_document("chunk-order")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add_all(
            [
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text="First chunk text.",
                    start=0,
                    end=17,
                    index=0,
                ),
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text=" Second chunk text.",
                    start=17,
                    end=36,
                    index=1,
                ),
            ]
        )
        await session.flush()

        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.index)
        )
        chunks = result.scalars().all()
        assert [c.index for c in chunks] == [0, 1]
        assert [c.text for c in chunks] == ["First chunk text.", " Second chunk text."]


@pytest.mark.anyio
async def test_duplicate_index_for_same_document_is_rejected() -> None:
    tenant_id, document_id = await _new_org_workspace_kb_document("chunk-dupe-index")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Chunk(tenant_id=tenant_id, document_id=document_id, text="A", start=0, end=1, index=0)
        )
        await session.flush()

        session.add(
            Chunk(tenant_id=tenant_id, document_id=document_id, text="B", start=1, end=2, index=0)
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.anyio
async def test_deleting_document_cascades_to_its_chunks() -> None:
    tenant_id, document_id = await _new_org_workspace_kb_document("chunk-cascade")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Chunk(tenant_id=tenant_id, document_id=document_id, text="A", start=0, end=1, index=0)
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = await session.get(Document, document_id)
        assert document is not None
        await session.delete(document)
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Chunk).where(Chunk.document_id == document_id))
        assert result.scalars().all() == []
