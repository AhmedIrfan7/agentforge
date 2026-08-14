"""Vector index maintenance (roadmap step 110) -- REINDEX CONCURRENTLY on
Chunk.embedding's ivfflat index (models/chunk.py, step 108/109).

A genuinely separate concern from step 108's embedding generation, matching
AGENTS.md SECTION "DOCUMENT PIPELINE OBSERVABILITY"'s own list, which
names "Embedding generation" and "Vector indexing" as adjacent but
distinct pipeline stages: 108 computes and stores a vector per chunk;
this task keeps the ANN index itself healthy as those vectors accumulate.

ivfflat indexes are approximate: their cell centroids are computed once,
at build/reindex time, from whatever data exists in the table right then.
Verified against pgvector's own documented guidance before building this
-- an ivfflat index built (or last reindexed) against a small or
unrepresentative sample of the real data distribution keeps degraded
recall permanently, not just temporarily, until it's rebuilt against more
representative data. `ix_chunks_embedding_ivfflat` was created by step
108/109's migration against an EMPTY `chunks` table (no rows existed
yet) -- by pgvector's own stated failure mode, it starts in exactly the
degraded state this task exists to fix, not a hypothetical future
concern.

`REINDEX INDEX CONCURRENTLY` (not a plain `REINDEX`, which takes an
exclusive lock and blocks reads/writes against `chunks` for its
duration -- unacceptable for a table live ingestion keeps writing to)
cannot run inside a transaction block; SQLAlchemy async connections
default to one, so this uses AUTOCOMMIT isolation explicitly (verified
live against real Postgres before trusting it).

Uses `settings.database_migrations_url`, not the app's normal
`database_url` -- see config.py's own docstring for why: REINDEX
requires index ownership on Postgres 16 (the `MAINTAIN` privilege that
would let the least-privilege `agentforge_app` role do this without
owning the index doesn't exist until Postgres 17), confirmed live
(`agentforge_app` gets `ERROR: must be owner of index`).

No scheduler dispatches this automatically -- docs/ROADMAP.md never adds
Celery Beat or any periodic-task infrastructure, so "background task"
here means a real, dispatchable Celery task, the same as every other
task in this codebase, not a task that also schedules itself. Whoever
operates a real deployment triggers this periodically (pgvector's own
guidance: monthly/quarterly, or after a large bulk-ingestion burst) --
same honest "build the task, not speculative scheduling infra" scope
`ping` (step 089) and every other task here has kept.
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from celery_app import celery_app
from config import settings

REINDEX_STATEMENT = text("REINDEX INDEX CONCURRENTLY ix_chunks_embedding_ivfflat")


async def _reindex_chunk_embeddings() -> None:
    # A dedicated, short-lived engine -- this task runs rarely (a
    # maintenance operation, not a per-request or per-document one), so
    # a persistent module-level engine alongside db.py's own would just
    # be an idle connection most of the time. db.py's engines
    # deliberately stay on database_url (least privilege); reusing them
    # here would mean smuggling migrations_url through a module that
    # exists specifically to keep app-runtime data access unprivileged.
    engine = create_async_engine(settings.database_migrations_url)
    try:
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(REINDEX_STATEMENT)
    finally:
        await engine.dispose()


@celery_app.task(name="reindex_chunk_embeddings")  # type: ignore[untyped-decorator]
def reindex_chunk_embeddings() -> None:
    asyncio.run(_reindex_chunk_embeddings())
