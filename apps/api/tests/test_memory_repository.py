"""Tests for repositories/memory.py (roadmap step 164). Duplicates the
small _new_org/_new_user/_cleanup_user helpers test_memory_model.py
already defines rather than importing them, matching this project's
own convention of only cross-importing test helpers from
tests/helpers.py, never test-module-to-test-module (established at
step 156).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from db import get_session, set_tenant_context
from models.assistant import Assistant
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.memory import Memory
from models.organization import Organization
from models.user import User
from models.workspace import Workspace
from repositories.memory import MemoryRepository


async def _new_org(slug: str) -> uuid.UUID:
    async with get_session() as session:
        org = Organization(name="Memory Repo Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await session.commit()
        return org.id


async def _new_conversation(tenant_id: uuid.UUID, slug: str) -> uuid.UUID:
    # session_id has a real FK to Conversation as of step 176 -- a
    # session-scoped Memory row needs a genuine one to point at.
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        workspace = Workspace(tenant_id=tenant_id, name="Mem Repo WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=tenant_id, workspace_id=workspace.id, name="Mem Repo KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        assistant = Assistant(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base.id,
            name="Mem Repo Bot",
            slug="bot",
        )
        session.add(assistant)
        await session.flush()

        conversation = Conversation(tenant_id=tenant_id, assistant_id=assistant.id)
        session.add(conversation)
        await session.flush()
        await session.commit()
        return conversation.id


async def _new_user(email: str) -> uuid.UUID:
    async with get_session() as session:
        user = User(email=email, full_name="Memory Repo Test User")
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
async def test_list_for_organization_orders_by_importance_score_descending() -> None:
    tenant_id = await _new_org("mem-repo-org-order")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        await repo.create(scope="organization", content="low", importance_score=0.2)
        await repo.create(scope="organization", content="high", importance_score=0.9)
        await repo.create(scope="organization", content="medium", importance_score=0.5)
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        memories = await repo.list_for_organization()

    assert [m.content for m in memories] == ["high", "medium", "low"]


@pytest.mark.anyio
async def test_list_for_organization_respects_min_importance() -> None:
    tenant_id = await _new_org("mem-repo-org-min")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        await repo.create(scope="organization", content="low", importance_score=0.2)
        await repo.create(scope="organization", content="high", importance_score=0.9)
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        memories = await repo.list_for_organization(min_importance=0.5)

    assert [m.content for m in memories] == ["high"]


@pytest.mark.anyio
async def test_list_for_user_is_isolated_per_user_and_excludes_other_scopes() -> None:
    tenant_id = await _new_org("mem-repo-user")
    user_a = await _new_user("mem-repo-user-a@example.com")
    user_b = await _new_user("mem-repo-user-b@example.com")
    try:
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            await repo.create(
                scope="user", user_id=user_a, content="a's memory", importance_score=0.5
            )
            await repo.create(
                scope="user", user_id=user_b, content="b's memory", importance_score=0.5
            )
            await repo.create(scope="organization", content="org memory", importance_score=0.9)
            await session.commit()

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            memories = await repo.list_for_user(user_a)

        assert [m.content for m in memories] == ["a's memory"]
    finally:
        await _cleanup_user(user_a)
        await _cleanup_user(user_b)


@pytest.mark.anyio
async def test_list_for_session_is_isolated_per_session() -> None:
    tenant_id = await _new_org("mem-repo-session")
    session_a = await _new_conversation(tenant_id, "mem-repo-session-a")
    session_b = await _new_conversation(tenant_id, "mem-repo-session-b")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        await repo.create(
            scope="session", session_id=session_a, content="a's turn", importance_score=0.5
        )
        await repo.create(
            scope="session", session_id=session_b, content="b's turn", importance_score=0.5
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        memories = await repo.list_for_session(session_a)

    assert [m.content for m in memories] == ["a's turn"]


@pytest.mark.anyio
async def test_delete_all_for_user_removes_only_that_users_memories() -> None:
    tenant_id = await _new_org("mem-repo-erase")
    user_a = await _new_user("mem-repo-erase-a@example.com")
    user_b = await _new_user("mem-repo-erase-b@example.com")
    try:
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            await repo.create(scope="user", user_id=user_a, content="a-1", importance_score=0.5)
            await repo.create(scope="user", user_id=user_a, content="a-2", importance_score=0.5)
            await repo.create(scope="user", user_id=user_b, content="b-1", importance_score=0.5)
            await repo.create(scope="organization", content="org-1", importance_score=0.5)
            await session.commit()

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            deleted_count = await repo.delete_all_for_user(user_a)
            await session.commit()

        assert deleted_count == 2

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            assert await repo.list_for_user(user_a) == []
            remaining_b = await repo.list_for_user(user_b)
            assert [m.content for m in remaining_b] == ["b-1"]
            remaining_org = await repo.list_for_organization()
            assert [m.content for m in remaining_org] == ["org-1"]
    finally:
        await _cleanup_user(user_a)
        await _cleanup_user(user_b)


@pytest.mark.anyio
async def test_update_content_mutates_and_persists_the_real_row() -> None:
    tenant_id = await _new_org("mem-repo-update")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        memory = await repo.create(scope="organization", content="original", importance_score=0.5)
        await session.commit()
        memory_id = memory.id

    new_expires_at = datetime.now(UTC) + timedelta(days=90)
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        existing = await repo.get(memory_id)
        assert existing is not None
        await repo.update_content(
            existing, content="updated", importance_score=0.9, expires_at=new_expires_at
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        fetched = await repo.get(memory_id)
        assert fetched is not None
        assert fetched.content == "updated"
        assert fetched.importance_score == 0.9
        assert fetched.expires_at == new_expires_at


@pytest.mark.anyio
async def test_created_memory_defaults_to_a_neutral_importance_score() -> None:
    tenant_id = await _new_org("mem-repo-default-score")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        memory = await repo.create(scope="organization", content="no score passed")
        await session.commit()

    assert isinstance(memory, Memory)
    assert memory.importance_score == 0.5
