"""Tenant-isolation tests for memory (roadmap step 171) -- proves the
real long-term memory access points built in steps 162-170
(`MemoryRepository.list_for_user`/`list_for_organization`/
`list_for_session`/`get`) cannot cross tenant boundaries, and that
Postgres RLS itself protects the `memories` table specifically --
`test_tenant_isolation.py` (the general RLS test, ADR-0003) only ever
exercised `Workspace`, never `Memory`. Same two-threat shape
`test_retrieval_tenant_isolation.py` already established for `Chunk`:
(1) a raw query bypassing every app-layer filter, proving RLS alone;
(2) a realistic attacker who has a genuinely REAL, valid id belonging
to another tenant (not a random never-real UUID, which
`test_memory_endpoints.py`'s own 404 tests already cover) and calls
the real repository methods with it under their OWN `tenant_id`.

`user_id` is a genuinely interesting case here that `Chunk`'s own
isolation tests didn't have to consider: `User` is a global identity
(`ARCHITECTURE.md`'s own tenant hierarchy doc), not tenant-scoped, so
the same real user COULD belong to more than one organization -- the
real question this file answers for `list_for_user` is whether
tenant A's repository leaks tenant B's memory for that same real user,
not whether the user id itself is guessable.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, set_tenant_context
from models.memory import Memory
from models.organization import Organization
from models.user import User
from repositories.memory import MemoryRepository


async def _seed_tenant(
    session: AsyncSession, *, slug: str, user_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org = Organization(name=f"Isolation {slug}", slug=f"memory-isolation-{slug}")
    session.add(org)
    await session.flush()
    await set_tenant_context(session, org.id)

    session.add(
        Memory(
            tenant_id=org.id,
            scope="organization",
            content=f"{slug} org fact",
            importance_score=0.7,
        )
    )
    await session.flush()

    session_id = uuid.uuid4()
    session.add(
        Memory(
            tenant_id=org.id,
            scope="session",
            session_id=session_id,
            content=f"{slug} session fact",
            importance_score=0.7,
        )
    )
    await session.flush()

    user_memory = Memory(
        tenant_id=org.id,
        scope="user",
        user_id=user_id,
        content=f"{slug} user fact",
        importance_score=0.7,
    )
    session.add(user_memory)
    await session.flush()

    return org.id, session_id, user_memory.id


@pytest.mark.anyio
async def test_memory_rows_are_invisible_across_tenants_via_rls() -> None:
    async with get_session() as session:
        user = User(email="mem-isolation-rls@example.com", full_name="Isolation Test")
        session.add(user)
        await session.flush()

        tenant_a, _session_a, _memory_a = await _seed_tenant(session, slug="rls-a", user_id=user.id)
        tenant_b, _session_b, memory_b = await _seed_tenant(session, slug="rls-b", user_id=user.id)

        await set_tenant_context(session, tenant_b)
        result = await session.execute(select(Memory).where(Memory.id == memory_b))
        assert result.scalar_one_or_none() is not None

        # Switch to tenant A's context and query the SAME memory id with
        # no tenant_id filter of its own -- RLS alone must hide it.
        await set_tenant_context(session, tenant_a)
        result = await session.execute(select(Memory).where(Memory.id == memory_b))
        assert result.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_get_returns_none_for_another_tenants_real_memory_id() -> None:
    async with get_session() as session:
        user = User(email="mem-isolation-get@example.com", full_name="Isolation Test")
        session.add(user)
        await session.flush()

        tenant_a, _session_a, _memory_a = await _seed_tenant(session, slug="get-a", user_id=user.id)
        _tenant_b, _session_b, memory_b = await _seed_tenant(session, slug="get-b", user_id=user.id)

        await set_tenant_context(session, tenant_a)
        repo = MemoryRepository(session, tenant_a)
        assert await repo.get(memory_b) is None


@pytest.mark.anyio
async def test_list_for_user_finds_nothing_for_the_same_real_user_under_another_tenant() -> None:
    async with get_session() as session:
        user = User(email="mem-isolation-user@example.com", full_name="Isolation Test")
        session.add(user)
        await session.flush()

        tenant_a, _session_a, _memory_a = await _seed_tenant(
            session, slug="user-a", user_id=user.id
        )
        await _seed_tenant(session, slug="user-b", user_id=user.id)

        # user.id genuinely has memory in tenant B (seeded above) -- the
        # real question is whether tenant A's own repository leaks it.
        await set_tenant_context(session, tenant_a)
        repo = MemoryRepository(session, tenant_a)
        results = await repo.list_for_user(user.id)

    assert [m.content for m in results] == ["user-a user fact"]


@pytest.mark.anyio
async def test_list_for_session_finds_nothing_with_another_tenants_real_session_id() -> None:
    async with get_session() as session:
        user = User(email="mem-isolation-session@example.com", full_name="Isolation Test")
        session.add(user)
        await session.flush()

        tenant_a, _session_a, _memory_a = await _seed_tenant(
            session, slug="session-a", user_id=user.id
        )
        _tenant_b, session_b, _memory_b = await _seed_tenant(
            session, slug="session-b", user_id=user.id
        )

        await set_tenant_context(session, tenant_a)
        repo = MemoryRepository(session, tenant_a)
        results = await repo.list_for_session(session_b)

    assert results == []


@pytest.mark.anyio
async def test_list_for_organization_never_returns_another_tenants_memory() -> None:
    async with get_session() as session:
        user = User(email="mem-isolation-org@example.com", full_name="Isolation Test")
        session.add(user)
        await session.flush()

        tenant_a, _session_a, _memory_a = await _seed_tenant(session, slug="org-a", user_id=user.id)
        await _seed_tenant(session, slug="org-b", user_id=user.id)

        await set_tenant_context(session, tenant_a)
        repo = MemoryRepository(session, tenant_a)
        results = await repo.list_for_organization()

    assert [m.content for m in results] == ["org-a org fact"]
