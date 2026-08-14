"""Chunk generation + batched embedding generation (roadmap step 108).

Two real, distinct pipeline stages folded into one task, not two separate
dispatches: AGENTS.md SECTION 6's canonical pipeline lists "chunk
generation" and "embedding" as adjacent stages, but docs/ROADMAP.md has
no numbered step of its own for chunk generation between 105 (the `Chunk`
model) and this one -- `models/chunk.py`'s own docstring already flagged
this gap explicitly and said whoever reaches 108 needs to either find the
dispatch already built or build it as part of getting embeddings
generated. There's nothing to embed without chunks existing first, so
building it here is the only way this step's literal ask ("batched
embedding generation") is possible at all.

Also folds in step 109's literal task (`Chunk.embedding`, the pgvector
column + ivfflat index) ahead of its own number for the identical
reason: computing an embedding with nowhere durable to store it would
mean throwing away a paid OpenAI API response, or inventing a throwaway
non-vector column just to replace it a step later -- both worse than
building the real, already-fully-specified (by 106/107's own interfaces)
schema now. `docs/ROADMAP.md`'s step 109 entry documents this and marks
itself done by reference rather than re-doing the work.

Dispatched from `extraction.py:dispatch_extraction` right after a
successful extraction (i.e. only once `Document.chunking_strategy` is
set) — same "one stage's success dispatches the next" shape
`upload_document` already established for kicking off extraction itself.

Known, accepted, real tension (not silently resolved): step 103's
chunking-strategy override endpoint lets a caller correct the
recommended strategy after extraction completes, but this task fires
immediately, with no waiting window. Once chunks + embeddings exist for
a document, overriding the strategy updates `Document.chunking_strategy`
but does NOT regenerate chunks — `models/chunk.py` already documents
re-chunking a document as a real, un-built future concern. A caller who
overrides after this task has already run keeps the old chunks/
embeddings until that future re-chunking capability exists. Worth
resurfacing if a later step (111's status endpoint, or a dedicated
re-chunk step) needs to make this state visible or actionable.

CHUNKERS reuses the same plain-dict-registry shape as `auth/oauth.py:
PROVIDERS` and `extraction.py:HANDLERS` — no reason for more machinery,
same reasoning both of those already gave.

As of step 112, dispatch_embedding_generation retries with exponential
backoff on any failure (autoretry_for/retry_backoff) -- before this,
despite max_retries=5 being set since this task's own introduction here,
nothing ever called self.retry() or configured autoretry_for, so a real
embedding failure (confirmed live at steps 108/111 -- an OpenAI request
failing closed) got exactly one attempt. Same accepted limitation as
extraction.py's own step-112 retry addition: this doesn't distinguish a
transient failure (worth retrying) from a permanent one (an invalid
API key, which will fail identically every retry) -- it burns the full
retry budget either way before landing on "embedding_failed".

As of step 114, _run_embedding_generation deletes any existing Chunk
rows for the document right before inserting the new ones -- the same
task now safely handles being dispatched a SECOND time for a document
that already has chunks (routers/document.py's new reindex endpoint is
what makes that reachable), rather than crashing on the (document_id,
index) unique constraint. Deletion happens only once the new
embeddings are already computed and ready to insert, in the same
commit as the insert -- if the embedding call itself fails, the OLD
chunks are untouched, so a failed re-index attempt never leaves a
document with zero chunks. This also closes a real, previously
documented tension: overriding a document's chunking_strategy (step
103) never used to actually regenerate its chunks -- that gap is
finally closeable now, via the reindex endpoint, not automatically.
"""

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import delete

from celery_app import celery_app
from chunking_fixed_size import chunk_fixed_size
from chunking_markdown_heading import chunk_markdown_heading
from chunking_recursive_hybrid import chunk_recursive_hybrid
from chunking_sentence_paragraph import chunk_sentence_paragraph
from chunking_table_aware import chunk_table_aware
from chunking_types import Chunk as ChunkData
from db import get_worker_session, set_tenant_context
from embeddings.base import EmbeddingProvider
from embeddings.openai import OpenAIEmbeddingProvider
from models.chunk import Chunk
from repositories.document import DocumentRepository

ChunkerFunction = Callable[[str], list[ChunkData]]

CHUNKERS: dict[str, ChunkerFunction] = {
    "fixed_size": chunk_fixed_size,
    "sentence_paragraph": chunk_sentence_paragraph,
    "markdown_heading": chunk_markdown_heading,
    "table_aware": chunk_table_aware,
    "recursive_hybrid": chunk_recursive_hybrid,
}

# OpenAI accepts up to 2048 inputs per embeddings request, but a smaller
# batch keeps any single request's size predictable and a mid-document
# failure from wasting an entire large document's worth of already-
# computed embeddings for nothing (a failed batch only forces a retry of
# that one batch, once retry/backoff lands in step 112 -- this step
# doesn't retry a failed batch itself, matching its own honest scope).
EMBEDDING_BATCH_SIZE = 100

_embedding_provider: EmbeddingProvider = OpenAIEmbeddingProvider()


async def _run_embedding_generation(document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    async with get_worker_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = DocumentRepository(session, tenant_id)
        document = await repo.get(document_id)
        if document is None or document.chunking_strategy is None:
            raise ValueError(
                f"document {document_id} has no chunking_strategy set -- "
                "this task must run after a successful extraction"
            )

        document.status = "embedding"
        await session.commit()
        # SET LOCAL only lasts one transaction (db.py:set_tenant_context's
        # own docstring) -- the commit above ended it.
        await set_tenant_context(session, tenant_id)

        chunker = CHUNKERS[document.chunking_strategy]
        raw_chunks = chunker(document.extracted_text or "")

        try:
            texts = [raw_chunk.text for raw_chunk in raw_chunks]
            vectors: list[list[float]] = []
            for batch_start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
                batch = texts[batch_start : batch_start + EMBEDDING_BATCH_SIZE]
                vectors.extend(await _embedding_provider.embed(batch))
        except Exception:
            document.status = "embedding_failed"
            await session.commit()
            raise

        # Delete any existing chunks only now that the new ones are
        # actually ready to replace them (step 114's re-index endpoint
        # is what makes this path reachable a second time for the same
        # document) -- deleting first and only then discovering the
        # embedding call above had failed would leave the document with
        # zero chunks, worse off than before the re-index was attempted.
        await session.execute(
            delete(Chunk).where(Chunk.document_id == document_id, Chunk.tenant_id == tenant_id)
        )
        session.add_all(
            Chunk(
                tenant_id=tenant_id,
                document_id=document_id,
                text=raw_chunk.text,
                start=raw_chunk.start,
                end=raw_chunk.end,
                index=raw_chunk.index,
                embedding=vector,
            )
            for raw_chunk, vector in zip(raw_chunks, vectors, strict=True)
        )
        document.status = "embedded"
        await session.commit()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="dispatch_embedding_generation",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def dispatch_embedding_generation(self: Any, document_id: str, tenant_id: str) -> None:
    asyncio.run(_run_embedding_generation(uuid.UUID(document_id), uuid.UUID(tenant_id)))
