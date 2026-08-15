"""Model-only test (roadmap step 177) -- no repository or CRUD endpoint
exists yet (message-send is step 179's own job), same "genuinely
model-only" precedent test_conversation_model.py (176) already
established one step ago. Exercises the ORM/RLS layer directly, since
there's no router to go through.
"""

import uuid

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from models.assistant import Assistant
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.message import Message
from models.organization import Organization
from models.workspace import Workspace


async def _new_conversation(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Message Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Msg WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Msg KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        assistant = Assistant(
            tenant_id=org.id, knowledge_base_id=knowledge_base.id, name="Msg Bot", slug="bot"
        )
        session.add(assistant)
        await session.flush()

        conversation = Conversation(tenant_id=org.id, assistant_id=assistant.id)
        session.add(conversation)
        await session.flush()
        await session.commit()
        return org.id, conversation.id


@pytest.mark.anyio
async def test_create_and_read_a_user_message() -> None:
    tenant_id, conversation_id = await _new_conversation("msg-create")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role="user",
            content="What's your refund policy?",
        )
        session.add(message)
        await session.flush()

        result = await session.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
        fetched = result.scalar_one()
        assert fetched.tenant_id == tenant_id
        assert fetched.conversation_id == conversation_id
        assert fetched.role == "user"
        assert fetched.content == "What's your refund policy?"


@pytest.mark.anyio
async def test_messages_preserve_insertion_order_via_created_at() -> None:
    tenant_id, conversation_id = await _new_conversation("msg-order")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                role="user",
                content="First turn.",
            )
        )
        await session.flush()
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                role="assistant",
                content="Second turn.",
            )
        )
        await session.flush()

        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        fetched = result.scalars().all()
        assert [m.content for m in fetched] == ["First turn.", "Second turn."]
        assert [m.role for m in fetched] == ["user", "assistant"]


@pytest.mark.anyio
async def test_deleting_the_conversation_cascades_to_its_messages() -> None:
    tenant_id, conversation_id = await _new_conversation("msg-cascade")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                role="user",
                content="Hello.",
            )
        )
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        conversation = await session.get(Conversation, conversation_id)
        assert conversation is not None
        await session.delete(conversation)
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
        assert result.scalars().all() == []
