"""Model-only test (roadmap step 176) -- no repository or CRUD endpoint
exists yet (neither is asked for until a later Milestone 6 step), same
"genuinely model-only" precedent test_chunk_model.py/test_assistant_model.py/
test_memory_model.py already established. Exercises the ORM/RLS layer
directly, since there's no router to go through.
"""

import uuid

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from models.assistant import Assistant
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.user import User
from models.workspace import Workspace


async def _new_org_workspace_kb_assistant(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Conversation Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Conv WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Conv KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        assistant = Assistant(
            tenant_id=org.id, knowledge_base_id=knowledge_base.id, name="Conv Bot", slug="bot"
        )
        session.add(assistant)
        await session.flush()
        await session.commit()
        return org.id, assistant.id


async def _new_user(email: str) -> uuid.UUID:
    async with get_session() as session:
        user = User(email=email, full_name="Conversation Test User")
        session.add(user)
        await session.flush()
        await session.commit()
        return user.id


async def _cleanup_user(user_id: uuid.UUID) -> None:
    # users is global, not tenant-scoped -- the org-slug cleanup every
    # other model test here relies on never touches it, same reasoning
    # test_memory_model.py's own _cleanup_user already established.
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
            await session.commit()


@pytest.mark.anyio
async def test_create_and_read_anonymous_conversation() -> None:
    """user_id is nullable -- a public deployment channel can have an
    anonymous visitor with no platform User row."""
    tenant_id, assistant_id = await _new_org_workspace_kb_assistant("conv-anon")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        conversation = Conversation(tenant_id=tenant_id, assistant_id=assistant_id)
        session.add(conversation)
        await session.flush()

        result = await session.execute(
            select(Conversation).where(Conversation.assistant_id == assistant_id)
        )
        fetched = result.scalar_one()
        assert fetched.tenant_id == tenant_id
        assert fetched.assistant_id == assistant_id
        assert fetched.user_id is None


@pytest.mark.anyio
async def test_create_and_read_conversation_with_a_user() -> None:
    tenant_id, assistant_id = await _new_org_workspace_kb_assistant("conv-user")
    user_id = await _new_user("conv-user@example.com")
    try:
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            conversation = Conversation(
                tenant_id=tenant_id, assistant_id=assistant_id, user_id=user_id
            )
            session.add(conversation)
            await session.flush()

            result = await session.execute(
                select(Conversation).where(Conversation.assistant_id == assistant_id)
            )
            fetched = result.scalar_one()
            assert fetched.user_id == user_id
    finally:
        await _cleanup_user(user_id)


@pytest.mark.anyio
async def test_deleting_the_assistant_cascades_to_its_conversations() -> None:
    tenant_id, assistant_id = await _new_org_workspace_kb_assistant("conv-cascade-asst")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(Conversation(tenant_id=tenant_id, assistant_id=assistant_id))
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        assistant = await session.get(Assistant, assistant_id)
        assert assistant is not None
        await session.delete(assistant)
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Conversation).where(Conversation.assistant_id == assistant_id)
        )
        assert result.scalars().all() == []


@pytest.mark.anyio
async def test_deleting_the_user_sets_conversation_user_id_to_null() -> None:
    """Deliberately SET NULL, not CASCADE -- unlike Memory.user_id, a
    conversation transcript should outlive the user who triggered it,
    same reasoning AuditLog.actor_user_id already established."""
    tenant_id, assistant_id = await _new_org_workspace_kb_assistant("conv-setnull-user")
    user_id = await _new_user("conv-setnull-user@example.com")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        conversation = Conversation(tenant_id=tenant_id, assistant_id=assistant_id, user_id=user_id)
        session.add(conversation)
        await session.commit()
        conversation_id = conversation.id

    async with get_session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        await session.delete(user)
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        fetched = await session.get(Conversation, conversation_id)
        assert fetched is not None
        assert fetched.user_id is None
