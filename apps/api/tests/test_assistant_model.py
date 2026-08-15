"""Model-only test (roadmap step 159) -- no repository or CRUD
endpoint exists yet (that's step 160's job, same "genuinely
model-only" precedent test_chunk_model.py already established at step
105). Exercises the ORM/RLS layer directly, since there's no router to
go through.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from agents.configuration import AgentConfiguration
from db import get_session, set_tenant_context
from models.assistant import Assistant
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace


async def _new_org_workspace_kb(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Assistant Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Asst WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Asst KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()
        await session.commit()
        return org.id, knowledge_base.id


@pytest.mark.anyio
async def test_create_and_read_assistant_within_tenant_context() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb("asst-create")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        assistant = Assistant(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            name="Support Bot",
            slug="support-bot",
            description="Answers customer questions.",
        )
        session.add(assistant)
        await session.flush()

        result = await session.execute(
            select(Assistant).where(Assistant.knowledge_base_id == kb_id)
        )
        fetched = result.scalar_one()
        assert fetched.tenant_id == tenant_id
        assert fetched.name == "Support Bot"
        assert fetched.slug == "support-bot"
        assert fetched.description == "Answers customer questions."
        # No agent_configuration passed -- the column's real default.
        assert fetched.agent_configuration == {}


@pytest.mark.anyio
async def test_agent_configuration_round_trips_real_data_through_jsonb() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb("asst-agent-config")
    config = AgentConfiguration(
        llm_provider="anthropic", enabled_agents=["retriever", "citation"], retrieval_top_k=15
    )

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        assistant = Assistant(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            name="Research Assistant",
            slug="research",
            agent_configuration=config.model_dump(),
        )
        session.add(assistant)
        await session.flush()

        result = await session.execute(
            select(Assistant).where(Assistant.knowledge_base_id == kb_id)
        )
        fetched = result.scalar_one()
        assert AgentConfiguration.model_validate(fetched.agent_configuration) == config


@pytest.mark.anyio
async def test_duplicate_slug_within_the_same_knowledge_base_is_rejected() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb("asst-dupe-slug")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Assistant(tenant_id=tenant_id, knowledge_base_id=kb_id, name="First", slug="bot")
        )
        await session.flush()

        session.add(
            Assistant(tenant_id=tenant_id, knowledge_base_id=kb_id, name="Second", slug="bot")
        )
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.anyio
async def test_deleting_knowledge_base_cascades_to_its_assistants() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb("asst-cascade")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(Assistant(tenant_id=tenant_id, knowledge_base_id=kb_id, name="Bot", slug="bot"))
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        knowledge_base = await session.get(KnowledgeBase, kb_id)
        assert knowledge_base is not None
        await session.delete(knowledge_base)
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            select(Assistant).where(Assistant.knowledge_base_id == kb_id)
        )
        assert result.scalars().all() == []
