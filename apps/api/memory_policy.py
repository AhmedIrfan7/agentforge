"""Memory expiration/TTL policy engine (roadmap step 168, AGENTS.md's
own "MEMORY LIFECYCLE" section: "Not everything deserves permanent
memory... Expiration.").

`compute_expiration` is the real policy: `importance_score` (164) is
already this codebase's one real signal for "how much does this memory
matter" -- expiration duration scales with it rather than inventing a
second, independent notion of importance. High-importance memories
(>= `_PERMANENT_THRESHOLD`) never expire (`None`) -- "not everything
deserves permanent memory" cuts both ways; something genuinely
important should stay permanent, not force-expire on a fixed schedule
regardless of value. Anything at or above
`agents/memory.py:RETENTION_THRESHOLD` (165, the same real bar
`memory_retrieval.py` (166) already reuses) but below permanent gets a
standard TTL; anything somehow below that threshold (shouldn't
normally exist -- `MemoryAgent` gates retention at exactly that bar)
gets a short one, a defensive floor rather than a real expected case.

`expire_stale_memories` is a real, dispatchable Celery task, scoped to
one tenant per call -- the same explicit `tenant_id` argument shape
every other real task in this codebase already uses
(`dispatch_embedding_generation`, `dispatch_memory_summarization`).
Not a scheduled/self-triggering job: this codebase never adds Celery
Beat or any periodic-task infrastructure, the same "build the task,
not speculative scheduling infra" precedent `vector_maintenance.py`'s
own step-110 docstring already established -- a real deployment's
operator triggers this periodically (looping over tenants is an
operational concern, not something this codebase has ever solved with
a special "iterate every tenant" task).
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete

from agents.memory import RETENTION_THRESHOLD
from celery_app import celery_app
from db import get_worker_session, set_tenant_context
from models.memory import Memory

_PERMANENT_THRESHOLD = 0.8
_STANDARD_TTL = timedelta(days=90)
_LOW_VALUE_TTL = timedelta(days=7)


def compute_expiration(importance_score: float, *, now: datetime | None = None) -> datetime | None:
    if importance_score >= _PERMANENT_THRESHOLD:
        return None

    reference = now or datetime.now(UTC)
    if importance_score >= RETENTION_THRESHOLD:
        return reference + _STANDARD_TTL
    return reference + _LOW_VALUE_TTL


async def _expire_stale_memories(tenant_id: uuid.UUID) -> None:
    async with get_worker_session() as session:
        await set_tenant_context(session, tenant_id)
        await session.execute(
            delete(Memory).where(
                Memory.tenant_id == tenant_id,
                Memory.expires_at.isnot(None),
                Memory.expires_at < datetime.now(UTC),
            )
        )
        await session.commit()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="expire_stale_memories",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def expire_stale_memories(self: Any, tenant_id: str) -> None:
    asyncio.run(_expire_stale_memories(uuid.UUID(tenant_id)))
