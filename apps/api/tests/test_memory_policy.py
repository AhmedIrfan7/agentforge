"""Tests for memory_policy.py (roadmap step 168). Duplicates the small
_new_org helper other memory test files already define rather than
importing it, matching this project's own test-module-isolation
convention (established at step 156).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from memory_policy import (
    _LOW_VALUE_TTL,
    _PERMANENT_THRESHOLD,
    _STANDARD_TTL,
    _expire_stale_memories,
    compute_expiration,
)
from models.memory import Memory
from models.organization import Organization
from repositories.memory import MemoryRepository


async def _new_org(slug: str) -> uuid.UUID:
    async with get_session() as session:
        org = Organization(name="Memory Policy Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await session.commit()
        return org.id


def test_high_importance_memory_never_expires() -> None:
    assert compute_expiration(_PERMANENT_THRESHOLD) is None
    assert compute_expiration(1.0) is None


def test_retained_memory_gets_the_standard_ttl() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    expires_at = compute_expiration(0.5, now=now)

    assert expires_at == now + _STANDARD_TTL


def test_below_retention_threshold_gets_a_short_ttl() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    expires_at = compute_expiration(0.1, now=now)

    assert expires_at == now + _LOW_VALUE_TTL


@pytest.mark.anyio
async def test_expire_stale_memories_deletes_only_past_expired_rows() -> None:
    tenant_id = await _new_org("mem-policy-expire")
    now = datetime.now(UTC)
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        await repo.create(
            scope="organization",
            content="expired",
            importance_score=0.6,
            expires_at=now - timedelta(days=1),
        )
        await repo.create(
            scope="organization",
            content="not yet expired",
            importance_score=0.6,
            expires_at=now + timedelta(days=1),
        )
        await repo.create(
            scope="organization", content="permanent", importance_score=0.9, expires_at=None
        )
        await session.commit()

    await _expire_stale_memories(tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        remaining = {m.content for m in result.scalars().all()}

    assert remaining == {"not yet expired", "permanent"}


@pytest.mark.anyio
async def test_expire_stale_memories_is_scoped_to_the_given_tenant() -> None:
    tenant_a = await _new_org("mem-policy-tenant-a")
    tenant_b = await _new_org("mem-policy-tenant-b")
    now = datetime.now(UTC)

    async with get_session() as session:
        await set_tenant_context(session, tenant_a)
        await MemoryRepository(session, tenant_a).create(
            scope="organization",
            content="a's expired memory",
            importance_score=0.6,
            expires_at=now - timedelta(days=1),
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_b)
        await MemoryRepository(session, tenant_b).create(
            scope="organization",
            content="b's expired memory",
            importance_score=0.6,
            expires_at=now - timedelta(days=1),
        )
        await session.commit()

    await _expire_stale_memories(tenant_a)

    async with get_session() as session:
        await set_tenant_context(session, tenant_a)
        result_a = await session.execute(select(Memory).where(Memory.tenant_id == tenant_a))
        assert result_a.scalars().all() == []

    async with get_session() as session:
        await set_tenant_context(session, tenant_b)
        result_b = await session.execute(select(Memory).where(Memory.tenant_id == tenant_b))
        assert len(result_b.scalars().all()) == 1
