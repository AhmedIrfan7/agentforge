"""Model-only test (roadmap step 219) -- no endpoint exists yet (step
220, voice-session-start, is what actually creates a VoiceSession).
Same "genuinely model-only" precedent test_document_model.py/
test_conversation_model.py already established. Exercises the ORM/RLS
layer directly, since there's no router to go through. A dedicated
cross-tenant RLS isolation proof is deliberately NOT duplicated here --
step 230 ("voice tenant-isolation test") is this codebase's own
explicit later home for that, same reasoning test_conversation_model.py
itself never duplicated one either.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from models.assistant import Assistant
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.voice_session import VoiceSession
from models.workspace import Workspace


async def _new_org_workspace_kb_assistant_conversation(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Voice Session Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Voice WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Voice KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        assistant = Assistant(
            tenant_id=org.id, knowledge_base_id=knowledge_base.id, name="Voice Bot", slug="bot"
        )
        session.add(assistant)
        await session.flush()

        conversation = Conversation(tenant_id=org.id, assistant_id=assistant.id)
        session.add(conversation)
        await session.flush()
        await session.commit()
        return org.id, conversation.id


@pytest.mark.anyio
async def test_create_and_read_voice_session_with_ended_at_defaulting_to_none() -> None:
    tenant_id, conversation_id = await _new_org_workspace_kb_assistant_conversation("voice-create")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(VoiceSession(tenant_id=tenant_id, conversation_id=conversation_id))
        await session.flush()

        result = await session.execute(
            select(VoiceSession).where(VoiceSession.conversation_id == conversation_id)
        )
        fetched = result.scalar_one()
        assert fetched.tenant_id == tenant_id
        assert fetched.ended_at is None


@pytest.mark.anyio
async def test_a_voice_session_can_be_marked_ended() -> None:
    tenant_id, conversation_id = await _new_org_workspace_kb_assistant_conversation("voice-end")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(VoiceSession(tenant_id=tenant_id, conversation_id=conversation_id))
        await session.flush()

        result = await session.execute(
            select(VoiceSession).where(VoiceSession.conversation_id == conversation_id)
        )
        voice_session = result.scalar_one()
        voice_session.ended_at = datetime.now(UTC)
        await session.flush()

        result = await session.execute(
            select(VoiceSession).where(VoiceSession.conversation_id == conversation_id)
        )
        fetched = result.scalar_one()
        assert fetched.ended_at is not None


@pytest.mark.anyio
async def test_a_conversation_can_have_more_than_one_voice_session() -> None:
    tenant_id, conversation_id = await _new_org_workspace_kb_assistant_conversation("voice-multi")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add_all(
            [
                VoiceSession(tenant_id=tenant_id, conversation_id=conversation_id),
                VoiceSession(tenant_id=tenant_id, conversation_id=conversation_id),
            ]
        )
        await session.flush()

        result = await session.execute(
            select(VoiceSession).where(VoiceSession.conversation_id == conversation_id)
        )
        assert len(result.scalars().all()) == 2


@pytest.mark.anyio
async def test_deleting_the_conversation_cascades_to_its_voice_sessions() -> None:
    tenant_id, conversation_id = await _new_org_workspace_kb_assistant_conversation("voice-cascade")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(VoiceSession(tenant_id=tenant_id, conversation_id=conversation_id))
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
            select(VoiceSession).where(VoiceSession.conversation_id == conversation_id)
        )
        assert result.scalars().all() == []
