"""Tests for embeddings_pipeline.py (roadmap step 108) -- exercises
_run_embedding_generation directly against real Postgres (same "no mocks
for infrastructure this project owns" reasoning test_extraction.py
already established), with a fake EmbeddingProvider swapped in via
monkeypatch instead of a real OpenAI call -- same reasoning
test_google_oauth_endpoints.py:FakeOAuthProvider already established for
swapping a whole provider rather than mocking HTTP calls inside a real
one, and avoids spending real money / needing a real OPENAI_API_KEY in
every future test run of this suite.
"""

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from embeddings_pipeline import EMBEDDING_BATCH_SIZE, _run_embedding_generation
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace


@dataclass
class _FakeEmbeddingProvider:
    # Chunk.embedding is a fixed pgvector(1536) column (models/chunk.py) --
    # a fake provider still has to return real 1536-length vectors to
    # insert successfully, the same way any real EmbeddingProvider would.
    name: str = "fake"
    dimensions: int = 1536
    call_batches: list[int] | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.call_batches is not None:
            self.call_batches.append(len(texts))
        return [[float(len(text))] * self.dimensions for text in texts]


async def _new_document(
    slug: str, *, extracted_text: str, chunking_strategy: str = "fixed_size"
) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Embeddings Pipeline Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Pipeline WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Pipeline KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        document = Document(
            tenant_id=org.id,
            knowledge_base_id=knowledge_base.id,
            title="doc.txt",
            storage_key=f"{slug}/doc.txt",
            content_type="text/plain",
            size_bytes=len(extracted_text),
            extracted_text=extracted_text,
            chunking_strategy=chunking_strategy,
            chunking_strategy_source="recommended",
            chunking_strategy_reasoning="test setup",
        )
        session.add(document)
        await session.flush()
        await session.commit()
        return org.id, document.id


@pytest.mark.anyio
async def test_generates_chunks_and_embeddings_for_a_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeEmbeddingProvider()
    monkeypatch.setattr("embeddings_pipeline._embedding_provider", fake)

    tenant_id, document_id = await _new_document(
        "embed-basic", extracted_text="First sentence here. Second sentence follows."
    )
    await _run_embedding_generation(document_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = await session.get(Document, document_id)
        assert document is not None
        assert document.status == "embedded"

        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.index)
        )
        chunks = result.scalars().all()
        assert len(chunks) >= 1
        assert [c.index for c in chunks] == list(range(len(chunks)))
        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == fake.dimensions


@pytest.mark.anyio
async def test_embed_is_called_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    call_batches: list[int] = []
    fake = _FakeEmbeddingProvider(call_batches=call_batches)
    monkeypatch.setattr("embeddings_pipeline._embedding_provider", fake)
    # A fixed-size chunker over a big enough text produces more chunks
    # than one batch -- proves multiple embed() calls happen, not one
    # giant request regardless of document size.
    monkeypatch.setattr("embeddings_pipeline.EMBEDDING_BATCH_SIZE", 2)

    text = "word " * 3000  # comfortably more than a few 1000-char chunks
    tenant_id, document_id = await _new_document("embed-batches", extracted_text=text)
    await _run_embedding_generation(document_id, tenant_id)

    assert len(call_batches) > 1
    assert all(size <= 2 for size in call_batches)


@pytest.mark.anyio
async def test_embedding_failure_marks_document_embedding_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingProvider:
        name = "failing"
        dimensions = 1536

        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("provider exploded")

    monkeypatch.setattr("embeddings_pipeline._embedding_provider", _FailingProvider())

    tenant_id, document_id = await _new_document("embed-failure", extracted_text="Some text.")
    with pytest.raises(RuntimeError):
        await _run_embedding_generation(document_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = await session.get(Document, document_id)
        assert document is not None
        assert document.status == "embedding_failed"


@pytest.mark.anyio
async def test_raises_when_document_has_no_chunking_strategy() -> None:
    async with get_session() as session:
        org = Organization(name="No Strategy Org", slug="embed-no-strategy-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)
        workspace = Workspace(tenant_id=org.id, name="WS", slug="embed-no-strategy-ws")
        session.add(workspace)
        await session.flush()
        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="KB", slug="embed-no-strategy-kb"
        )
        session.add(knowledge_base)
        await session.flush()
        document = Document(
            tenant_id=org.id,
            knowledge_base_id=knowledge_base.id,
            title="doc.txt",
            storage_key="embed-no-strategy/doc.txt",
            content_type="text/plain",
            size_bytes=4,
            extracted_text="text",
        )
        session.add(document)
        await session.flush()
        await session.commit()
        tenant_id, document_id = org.id, document.id

    with pytest.raises(ValueError, match="chunking_strategy"):
        await _run_embedding_generation(document_id, tenant_id)


def test_embedding_batch_size_is_positive() -> None:
    assert EMBEDDING_BATCH_SIZE > 0


@pytest.mark.anyio
async def test_rerunning_replaces_old_chunks_not_duplicates_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Roadmap step 114 -- the reindex endpoint dispatches this exact
    task a second time for a document that already has chunks. Without
    deleting the old rows first, the second run's inserts would collide
    on (document_id, index) instead of replacing anything."""
    monkeypatch.setattr("embeddings_pipeline._embedding_provider", _FakeEmbeddingProvider())

    tenant_id, document_id = await _new_document(
        "embed-rerun", extracted_text="First sentence here. Second sentence follows."
    )
    await _run_embedding_generation(document_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.index)
        )
        first_run_ids = [c.id for c in result.scalars().all()]

    await _run_embedding_generation(document_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = await session.get(Document, document_id)
        assert document is not None
        assert document.status == "embedded"

        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.index)
        )
        chunks = result.scalars().all()
        assert [c.index for c in chunks] == list(range(len(chunks)))
        # Genuinely replaced, not appended to -- same count, different
        # row identities.
        assert len(chunks) == len(first_run_ids)
        assert [c.id for c in chunks] != first_run_ids


@pytest.mark.anyio
async def test_failed_rerun_leaves_old_chunks_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    """A re-index attempt that fails during embedding must not delete
    the still-working chunks from the previous successful run -- deleting
    first and only then discovering the new embeddings failed would leave
    the document with zero chunks, worse than before the retry."""
    monkeypatch.setattr("embeddings_pipeline._embedding_provider", _FakeEmbeddingProvider())
    tenant_id, document_id = await _new_document(
        "embed-rerun-fail", extracted_text="First sentence here. Second sentence follows."
    )
    await _run_embedding_generation(document_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.index)
        )
        original_ids = [c.id for c in result.scalars().all()]
        assert len(original_ids) >= 1

    class _FailingProvider:
        name = "failing"
        dimensions = 1536

        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("provider exploded on rerun")

    monkeypatch.setattr("embeddings_pipeline._embedding_provider", _FailingProvider())
    with pytest.raises(RuntimeError):
        await _run_embedding_generation(document_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = await session.get(Document, document_id)
        assert document is not None
        assert document.status == "embedding_failed"

        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.index)
        )
        chunks = result.scalars().all()
        assert [c.id for c in chunks] == original_ids
