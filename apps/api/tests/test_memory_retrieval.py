"""Tests for memory_retrieval.py (roadmap step 166). Duplicates the
small _new_org/_new_user/_cleanup_user helpers test_memory_model.py/
test_memory_repository.py already define rather than importing them,
matching this project's own test-module-isolation convention
(established at step 156).
"""

import uuid

import pytest

from db import get_session, set_tenant_context
from memory_retrieval import retrieve_memory_for_conversation_start
from models.organization import Organization
from models.user import User
from repositories.memory import MemoryRepository


async def _new_org(slug: str) -> uuid.UUID:
    async with get_session() as session:
        org = Organization(name="Memory Retrieval Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await session.commit()
        return org.id


async def _new_user(email: str) -> uuid.UUID:
    async with get_session() as session:
        user = User(email=email, full_name="Memory Retrieval Test User")
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
async def test_retrieval_combines_user_and_organization_memory_by_importance() -> None:
    tenant_id = await _new_org("mem-retrieval-combine")
    user_id = await _new_user("mem-retrieval-combine@example.com")
    try:
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            await repo.create(
                scope="user", user_id=user_id, content="user pref", importance_score=0.6
            )
            await repo.create(scope="organization", content="org fact", importance_score=0.95)
            await session.commit()

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            memories = await retrieve_memory_for_conversation_start(session, tenant_id, user_id)

        assert [m.content for m in memories] == ["org fact", "user pref"]
    finally:
        await _cleanup_user(user_id)


@pytest.mark.anyio
async def test_retrieval_excludes_memory_below_the_default_retention_threshold() -> None:
    tenant_id = await _new_org("mem-retrieval-threshold")
    user_id = await _new_user("mem-retrieval-threshold@example.com")
    try:
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            await repo.create(
                scope="user", user_id=user_id, content="low value", importance_score=0.3
            )
            await repo.create(
                scope="user", user_id=user_id, content="high value", importance_score=0.8
            )
            await session.commit()

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            memories = await retrieve_memory_for_conversation_start(session, tenant_id, user_id)

        assert [m.content for m in memories] == ["high value"]
    finally:
        await _cleanup_user(user_id)


@pytest.mark.anyio
async def test_retrieval_is_isolated_to_the_given_user() -> None:
    tenant_id = await _new_org("mem-retrieval-isolation")
    user_a = await _new_user("mem-retrieval-isolation-a@example.com")
    user_b = await _new_user("mem-retrieval-isolation-b@example.com")
    try:
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            await repo.create(
                scope="user", user_id=user_a, content="a's memory", importance_score=0.7
            )
            await repo.create(
                scope="user", user_id=user_b, content="b's memory", importance_score=0.9
            )
            await session.commit()

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            memories = await retrieve_memory_for_conversation_start(session, tenant_id, user_a)

        assert [m.content for m in memories] == ["a's memory"]
    finally:
        await _cleanup_user(user_a)
        await _cleanup_user(user_b)


@pytest.mark.anyio
async def test_retrieval_respects_the_overall_limit_across_both_scopes() -> None:
    tenant_id = await _new_org("mem-retrieval-limit")
    user_id = await _new_user("mem-retrieval-limit@example.com")
    try:
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            for i in range(3):
                await repo.create(
                    scope="user",
                    user_id=user_id,
                    content=f"user-{i}",
                    importance_score=0.9,
                )
            for i in range(3):
                await repo.create(scope="organization", content=f"org-{i}", importance_score=0.6)
            await session.commit()

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            memories = await retrieve_memory_for_conversation_start(
                session, tenant_id, user_id, limit=4
            )

        assert len(memories) == 4
        # The three highest-importance (user, 0.9) entries come first,
        # then the single highest-importance org entry fills the rest.
        assert all(m.importance_score == 0.9 for m in memories[:3])
        assert memories[3].importance_score == 0.6
    finally:
        await _cleanup_user(user_id)
