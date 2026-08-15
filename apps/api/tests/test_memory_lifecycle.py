"""Memory-lifecycle tests (roadmap step 174) -- one comprehensive
create -> retrieve -> expire -> delete narrative walking a real
`Memory` row through every real stage built across steps 162-173,
distinct from the many per-component unit/integration tests already
covering each stage in isolation:

  create   -- MemoryRepository.create() (164)
  retrieve -- memory_retrieval.py:retrieve_memory_for_conversation_start (166)
  expire   -- memory_policy.py:compute_expiration/_expire_stale_memories (168)
  delete   -- MemoryRepository.delete() (169's own granular per-entry delete)

Uses `MemoryRepository.create()` directly for the "create" stage
rather than the full `MemoryAgent`+`memory_summarization.py` path --
this test is about the `Memory` row's own real state transitions, not
re-proving summarization's own separate retention-decision logic
(already covered in `test_memory_summarization.py`).

The roadmap names expiration and deletion as two DISTINCT stages, so
two separate memories are used throughout: one that expires via the
real TTL policy sweep, one that's explicitly deleted -- proving both
real removal mechanisms independently rather than conflating them.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from db import get_session, set_tenant_context
from memory_policy import _expire_stale_memories, compute_expiration
from memory_retrieval import retrieve_memory_for_conversation_start
from models.organization import Organization
from models.user import User
from repositories.memory import MemoryRepository


async def _new_org(slug: str) -> uuid.UUID:
    async with get_session() as session:
        org = Organization(name="Memory Lifecycle Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await session.commit()
        return org.id


async def _new_user(email: str) -> uuid.UUID:
    async with get_session() as session:
        user = User(email=email, full_name="Memory Lifecycle Test User")
        session.add(user)
        await session.flush()
        await session.commit()
        return user.id


async def _cleanup_user(user_id: uuid.UUID) -> None:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
            await session.commit()


@pytest.mark.anyio
async def test_full_memory_lifecycle_create_retrieve_expire_delete() -> None:
    tenant_id = await _new_org("mem-lifecycle")
    user_id = await _new_user("mem-lifecycle@example.com")
    try:
        # --- create ---------------------------------------------------
        # A high-importance memory (compute_expiration gives it no
        # expiration -- it will be explicitly deleted, not expired) and
        # a low-importance one with a real near-future expiration
        # (compute_expiration's own real 7-day low-value TTL) -- still
        # genuinely alive at creation time.
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            permanent = await repo.create(
                scope="user",
                user_id=user_id,
                content="Jordan's account is on the enterprise plan.",
                importance_score=0.9,
                expires_at=compute_expiration(0.9),
            )
            expiring = await repo.create(
                scope="user",
                user_id=user_id,
                content="Jordan asked about a one-time promo code.",
                importance_score=0.2,
                expires_at=compute_expiration(0.2),
            )
            await session.commit()
            permanent_id = permanent.id
            expiring_id = expiring.id

        assert compute_expiration(0.9) is None
        assert compute_expiration(0.2) is not None

        # --- retrieve ---------------------------------------------------
        # Both are genuinely visible via the real identity-based
        # retrieval path before anything has expired or been deleted.
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            retrieved = await retrieve_memory_for_conversation_start(
                session, tenant_id, user_id, min_importance=0.0
            )
        assert {m.id for m in retrieved} == {permanent_id, expiring_id}

        # --- expire ---------------------------------------------------
        # Simulates real time passing: backdate the low-importance
        # memory's expires_at into the past (a test can't actually wait
        # seven real days for its own TTL to lapse), then run the real
        # sweep -- it removes exactly that one row.
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            still_expiring = await repo.get(expiring_id)
            assert still_expiring is not None
            await repo.update_content(
                still_expiring,
                content=still_expiring.content,
                importance_score=still_expiring.importance_score,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
            await session.commit()

        await _expire_stale_memories(tenant_id)

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            after_expiry = await retrieve_memory_for_conversation_start(
                session, tenant_id, user_id, min_importance=0.0
            )
        assert {m.id for m in after_expiry} == {permanent_id}

        # --- delete -----------------------------------------------------
        # The surviving (permanent) memory is explicitly deleted --
        # step 169's own granular, individual-entry operation, distinct
        # from the automatic sweep above.
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            remaining = await repo.get(permanent_id)
            assert remaining is not None
            await repo.delete(remaining)
            await session.commit()

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            final = await retrieve_memory_for_conversation_start(
                session, tenant_id, user_id, min_importance=0.0
            )
        assert final == []
    finally:
        await _cleanup_user(user_id)
