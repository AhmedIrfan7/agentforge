"""Tenant-isolation tests for retrieval (roadmap step 132) --
proves the real retrieval entry points built in steps 120-131
(ChunkRepository.search_by_keyword/get_expanded_context, PgVectorStore.
search) cannot cross tenant boundaries, and that Postgres RLS itself
protects the `chunks` table specifically -- test_tenant_isolation.py
(the general RLS test, ADR-0003) only ever exercised `Workspace`, never
`Chunk`.

Two distinct threats are tested, not just one: (1) a raw query bypassing
every app-layer filter -- proves RLS alone, the same "no rows found even
without an app-layer WHERE clause" pattern test_tenant_isolation.py
already established; (2) a realistic attacker who has (guessed, leaked,
enumerated) another tenant's REAL, valid knowledge_base_id or chunk_id
and calls the real retrieval methods with it under their OWN tenant_id
-- a materially stronger test than the existing per-endpoint 404 tests
(test_retrieval_endpoints.py), which only ever use a random, never-real
UUID, not a genuinely valid id belonging to someone else.

Same flush(), never commit() discipline as test_tenant_isolation.py
for every test but one: PgVectorStore.search() (step 119) opens its
OWN session via get_worker_session(), a different connection than a
test's own get_session() -- flushed-but-uncommitted rows in one
session are invisible to another, so the dense-search test has no
choice but to commit, and therefore does need its own explicit cleanup
(same per-model delete shape test_retrieval_endpoints.py's own
_cleanup_org already established), unlike every other test here.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, set_tenant_context
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace
from repositories.chunk import ChunkRepository
from vectorstore.pgvector import PgVectorStore


def _vector(*, lead: float) -> list[float]:
    return [lead] + [0.01] * 1535


async def _seed_tenant(
    session: AsyncSession, *, slug: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org = Organization(name=f"Isolation {slug}", slug=f"retrieval-isolation-{slug}")
    session.add(org)
    await session.flush()
    await set_tenant_context(session, org.id)

    workspace = Workspace(tenant_id=org.id, name=f"{slug} WS", slug=f"{slug}-ws")
    session.add(workspace)
    await session.flush()

    knowledge_base = KnowledgeBase(
        tenant_id=org.id, workspace_id=workspace.id, name=f"{slug} KB", slug=f"{slug}-kb"
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

    chunk = Chunk(
        tenant_id=org.id,
        document_id=document.id,
        text="refund policy allows returns within thirty days",
        start=0,
        end=1,
        index=0,
        embedding=_vector(lead=1.0),
    )
    session.add(chunk)
    await session.flush()

    return org.id, knowledge_base.id, chunk.id


@pytest.mark.anyio
async def test_chunk_rows_are_invisible_across_tenants_via_rls() -> None:
    async with get_session() as session:
        _tenant_a, _kb_a, _chunk_a = await _seed_tenant(session, slug="rls-a")
        tenant_b, _kb_b, chunk_b = await _seed_tenant(session, slug="rls-b")

        await set_tenant_context(session, tenant_b)
        result = await session.execute(select(Chunk).where(Chunk.id == chunk_b))
        assert result.scalar_one_or_none() is not None

        # Switch to tenant A's context and query the SAME chunk id with
        # no tenant_id filter of its own -- RLS alone must hide it.
        await set_tenant_context(session, _tenant_a)
        result = await session.execute(select(Chunk).where(Chunk.id == chunk_b))
        assert result.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_keyword_search_finds_nothing_with_another_tenants_real_knowledge_base_id() -> None:
    async with get_session() as session:
        tenant_a, _kb_a, _chunk_a = await _seed_tenant(session, slug="kw-a")
        _tenant_b, kb_b, _chunk_b = await _seed_tenant(session, slug="kw-b")

        await set_tenant_context(session, tenant_a)
        repo = ChunkRepository(session, tenant_a)
        results = await repo.search_by_keyword(kb_b, "refund policy", top_k=10)

    assert results == []


@pytest.mark.anyio
async def test_expand_to_parent_raises_for_another_tenants_real_chunk_id() -> None:
    async with get_session() as session:
        tenant_a, _kb_a, _chunk_a = await _seed_tenant(session, slug="parent-a")
        _tenant_b, _kb_b, chunk_b = await _seed_tenant(session, slug="parent-b")

        await set_tenant_context(session, tenant_a)
        repo = ChunkRepository(session, tenant_a)

        with pytest.raises(ValueError, match="does not exist"):
            await repo.get_expanded_context(chunk_b)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Chunk, Document, KnowledgeBase, Workspace):
            result = await session.execute(select(model).where(model.tenant_id == org_id))
            for row in result.scalars().all():
                await session.delete(row)
            await session.flush()
        org = await session.get(Organization, org_id)
        if org is not None:
            await session.delete(org)
        await session.commit()


@pytest.mark.anyio
async def test_dense_search_finds_nothing_with_another_tenants_real_knowledge_base_id() -> None:
    async with get_session() as session:
        tenant_a, _kb_a, _chunk_a = await _seed_tenant(session, slug="dense-a")
        tenant_b, kb_b, _chunk_b = await _seed_tenant(session, slug="dense-b")
        await session.commit()

    try:
        store = PgVectorStore()
        results = await store.search(tenant_a, kb_b, _vector(lead=1.0), top_k=10)
        assert results == []
    finally:
        await _cleanup_org(tenant_a)
        await _cleanup_org(tenant_b)
