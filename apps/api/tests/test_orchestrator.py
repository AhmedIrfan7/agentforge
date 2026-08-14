"""Tests for orchestrator.py (roadmap steps 140-143) -- proves the real
LangGraph plumbing behind Orchestrator.handle() actually works end to
end, that it's a genuine service holding a real AgentRegistry
dependency (not a bare function), and that the real intent-analysis
(141), planning (142), and retriever-execution (143) nodes correctly
set internal graph state. The retriever step is tested against real
Postgres (same "no mocks for infrastructure this project owns"
reasoning test_retriever_agent.py already established) -- it's the
one real mechanism (keyword search) that works with no OPENAI_API_KEY.
"""

import uuid

import pytest

from agents.registry import AgentRegistry
from db import get_session, set_tenant_context
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace
from orchestrator import Orchestrator, _classify_intent


async def _new_org_workspace_kb(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Orchestrator Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Orch WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Orch KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()
        await session.commit()
        return org.id, knowledge_base.id


async def _new_org_workspace_kb_with_chunk(slug: str, *, text: str) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, kb_id = await _new_org_workspace_kb(slug)
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=kb_id,
            title="doc.txt",
            storage_key=f"{slug}/doc.txt",
            content_type="text/plain",
            size_bytes=10,
        )
        session.add(document)
        await session.flush()
        session.add(
            Chunk(tenant_id=tenant_id, document_id=document.id, text=text, start=0, end=1, index=0)
        )
        await session.commit()
    return tenant_id, kb_id


def test_orchestrator_holds_the_registry_it_was_constructed_with() -> None:
    registry = AgentRegistry()
    orchestrator = Orchestrator(registry)

    assert orchestrator._registry is registry


@pytest.mark.anyio
async def test_each_orchestrator_instance_builds_its_own_independent_graph() -> None:
    first = Orchestrator(AgentRegistry())
    second = Orchestrator(AgentRegistry())

    assert first._graph is not second._graph


def test_classify_intent_recognizes_a_real_query_as_document_search() -> None:
    assert _classify_intent("find the refund policy") == "document_search"


def test_classify_intent_recognizes_an_empty_query() -> None:
    assert _classify_intent("") == "empty"


def test_classify_intent_recognizes_a_whitespace_only_query_as_empty() -> None:
    assert _classify_intent("   \n\t  ") == "empty"


@pytest.mark.anyio
async def test_a_blank_query_short_circuits_to_an_echoed_empty_response() -> None:
    """No real DB work happens for an empty query -- intent is "empty",
    agent_names stays [], and _execute_node's echo fallback fires."""
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator._graph.ainvoke(
        {
            "query": "   ",
            "tenant_id": uuid.uuid4(),
            "knowledge_base_id": uuid.uuid4(),
            "intent": "",
            "agent_names": [],
            "response": "",
        }
    )

    assert result["intent"] == "empty"
    assert result["agent_names"] == []
    assert result["response"] == "   "


@pytest.mark.anyio
async def test_a_real_query_plans_to_run_the_retriever() -> None:
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator._graph.ainvoke(
        {
            "query": "find the refund policy",
            "tenant_id": uuid.uuid4(),
            "knowledge_base_id": uuid.uuid4(),
            "intent": "",
            "agent_names": [],
            "response": "",
        }
    )

    assert result["intent"] == "document_search"
    assert result["agent_names"] == ["retriever"]


@pytest.mark.anyio
async def test_handle_returns_no_results_message_when_nothing_matches() -> None:
    """A real, seeded (but empty) knowledge base -- verified live first
    that a genuinely random, never-seeded tenant/kb pair also just
    returns zero rows (no FK enforcement on a SELECT), so a real org is
    used here anyway for a more realistic, honest scope, not because
    it's required to avoid an error."""
    tenant_id, kb_id = await _new_org_workspace_kb("orch-handle-empty")
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator.handle(
        "find the refund policy", tenant_id=tenant_id, knowledge_base_id=kb_id
    )

    assert result == "No results found."


@pytest.mark.anyio
async def test_handle_returns_real_retrieved_chunk_text() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb_with_chunk(
        "orch-handle-hit", text="Our refund policy allows returns within thirty days."
    )
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator.handle(
        "refund policy", tenant_id=tenant_id, knowledge_base_id=kb_id
    )

    assert result == "Our refund policy allows returns within thirty days."


@pytest.mark.anyio
async def test_handle_is_scoped_to_the_given_knowledge_base() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb_with_chunk(
        "orch-handle-scope", text="refund policy details"
    )
    other_tenant_id, other_kb_id = await _new_org_workspace_kb("orch-handle-scope-other")
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator.handle(
        "refund policy", tenant_id=other_tenant_id, knowledge_base_id=other_kb_id
    )

    assert result == "No results found."
    assert tenant_id != other_tenant_id
    assert kb_id != other_kb_id
