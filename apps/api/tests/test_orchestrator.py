"""Tests for orchestrator.py (roadmap steps 140-143) -- proves the real
LangGraph plumbing behind Orchestrator.handle() actually works end to
end, that it's a genuine service holding a real AgentRegistry
dependency (not a bare function), and that the real intent-analysis
(141), planning (142), and retriever-execution (143) nodes correctly
set internal graph state. The retriever step is tested against real
Postgres (same "no mocks for infrastructure this project owns"
reasoning test_retriever_agent.py already established) -- it's the
one real mechanism (keyword search) that works with no OPENAI_API_KEY.

As of step 157, also covers the orchestrator integration test the
roadmap's own parenthetical asks for: "full request->response trace."
Every test above already proves handle()'s real RESPONSE value is
correct; none of them prove the request is actually TRACED end to end
-- agents/tracing.py's traced_run (153) is wired into _planning_node/
_execute_node, but nothing until now called handle() inside
structlog.testing.capture_logs() to verify the "agent_execution" event
this project's own tracing infrastructure promises actually fires for
every real per-agent step a request triggers, and only those steps --
tying steps 140-143 (the orchestrator itself) and 153 (tracing)
together into one integration-level guarantee neither step alone
proves on its own.
"""

import uuid
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any

import pytest
import structlog.testing

import orchestrator as orchestrator_module
from agents.conversation import ConversationAgent
from agents.registry import AgentRegistry
from agents.retriever import RetrievedChunk
from db import get_session, set_tenant_context
from llm.base import LLMResponse, Message
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
            "chunks": [],
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
            "chunks": [],
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

    assert result.response == "No results found."
    assert result.chunks == []


@pytest.mark.anyio
async def test_handle_returns_real_retrieved_chunk_text() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb_with_chunk(
        "orch-handle-hit", text="Our refund policy allows returns within thirty days."
    )
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator.handle(
        "refund policy", tenant_id=tenant_id, knowledge_base_id=kb_id
    )

    assert result.response == "Our refund policy allows returns within thirty days."
    # As of step 187 -- the real chunks that fed the response, so a
    # caller (routers/conversation.py) can build real citations.
    assert len(result.chunks) == 1
    assert result.chunks[0].text == "Our refund policy allows returns within thirty days."


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

    assert result.response == "No results found."
    assert tenant_id != other_tenant_id
    assert kb_id != other_kb_id


def _agent_execution_events(
    logs: list[MutableMapping[str, Any]],
) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == "agent_execution"]


@pytest.mark.anyio
async def test_handle_produces_a_full_trace_across_every_real_agent_step() -> None:
    """A real document-search request runs two real, traced agent
    steps -- planning (142) then retriever (143) -- and nothing else;
    this asserts the real response AND that both, and only both, are
    traced, in the order the graph actually runs them."""
    tenant_id, kb_id = await _new_org_workspace_kb_with_chunk(
        "orch-trace-hit", text="Our refund policy allows returns within thirty days."
    )
    orchestrator = Orchestrator(AgentRegistry())

    with structlog.testing.capture_logs() as logs:
        result = await orchestrator.handle(
            "refund policy", tenant_id=tenant_id, knowledge_base_id=kb_id
        )

    assert result.response == "Our refund policy allows returns within thirty days."
    events = _agent_execution_events(logs)
    assert [e["agent_name"] for e in events] == ["planning", "retriever"]
    assert all(e["status"] == "success" for e in events)


@pytest.mark.anyio
async def test_handle_traces_planning_but_not_retriever_for_an_empty_query() -> None:
    """_planning_node always runs (140-141's own graph shape means
    every request reaches it); _execute_node's echo short-circuit for
    an empty query means the retriever agent is never constructed or
    called -- the trace should honestly reflect that, not claim a step
    ran that didn't."""
    orchestrator = Orchestrator(AgentRegistry())

    with structlog.testing.capture_logs() as logs:
        result = await orchestrator.handle(
            "   ", tenant_id=uuid.uuid4(), knowledge_base_id=uuid.uuid4()
        )

    assert result.response == "   "
    events = _agent_execution_events(logs)
    assert [e["agent_name"] for e in events] == ["planning"]


@dataclass
class _FakeHybridRetrieverAgent:
    """Stands in for the real RetrieverAgent's search_hybrid -- avoids a
    real OPENAI_API_KEY embedding call (network + cost) while still
    proving _RetrieverGraphAgent.run() actually calls search_hybrid, not
    search_keyword, once settings.openai_api_key is truthy."""

    chunks: list[RetrievedChunk]
    received_queries: list[str] = field(default_factory=list)

    async def search_hybrid(
        self,
        tenant_id: uuid.UUID,
        chunk_repo: object,
        knowledge_base_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        filters: object | None = None,
    ) -> list[RetrievedChunk]:
        self.received_queries.append(query)
        return self.chunks


@dataclass
class _RecordingLLMProvider:
    name: str = "fake"
    response_content: str = "a real generated answer"
    received_messages: list[list[Message]] = field(default_factory=list)

    async def complete(self, messages: list[Message]) -> LLMResponse:
        self.received_messages.append(messages)
        return LLMResponse(content=self.response_content, prompt_tokens=10, completion_tokens=5)


@pytest.mark.anyio
async def test_handle_uses_hybrid_retrieval_and_real_generation_when_a_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact gap the user hit live: a natural-language question whose
    words don't all literally appear in the source text returned a raw
    chunk dump (or "No results found.") from keyword-only search with no
    generation model. With a real key configured, the graph must call
    search_hybrid (not search_keyword) and phrase the answer through a
    real ConversationAgent -- proven here via fakes standing in for the
    real embedding/LLM providers, so this test needs no real network
    call or API key."""
    tenant_id, kb_id = await _new_org_workspace_kb_with_chunk(
        "orch-hybrid-gen", text="Ahmed has experience with React and FastAPI."
    )
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        text="Ahmed has experience with React and FastAPI.",
        score=0.95,
    )
    fake_retriever = _FakeHybridRetrieverAgent(chunks=[chunk])
    fake_llm = _RecordingLLMProvider(response_content="Yes, he has React and FastAPI experience.")

    monkeypatch.setattr(orchestrator_module, "settings", _TruthyKeySettings())
    monkeypatch.setattr(orchestrator_module, "_retriever_agent", fake_retriever)
    monkeypatch.setattr(orchestrator_module, "_conversation_agent", ConversationAgent(fake_llm))

    orchestrator = Orchestrator(AgentRegistry())
    result = await orchestrator.handle(
        "does he have any experience", tenant_id=tenant_id, knowledge_base_id=kb_id
    )

    assert result.response == "Yes, he has React and FastAPI experience."
    assert result.chunks == [chunk]
    assert fake_retriever.received_queries == ["does he have any experience"]
    sent_user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user")
    assert "React and FastAPI" in sent_user_message.content
    assert "does he have any experience" in sent_user_message.content


@pytest.mark.anyio
async def test_handle_generates_an_honest_answer_when_hybrid_retrieval_finds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the same bug report: "No results found." was
    dishonest -- it reads like an error, not an answer. With a key
    configured, an empty-chunks result must still go through the real
    ConversationAgent and come back as a real, honest sentence."""
    tenant_id, kb_id = await _new_org_workspace_kb("orch-hybrid-empty")
    fake_retriever = _FakeHybridRetrieverAgent(chunks=[])
    fake_llm = _RecordingLLMProvider(response_content="No, he does not have a PhD mentioned.")

    monkeypatch.setattr(orchestrator_module, "settings", _TruthyKeySettings())
    monkeypatch.setattr(orchestrator_module, "_retriever_agent", fake_retriever)
    monkeypatch.setattr(orchestrator_module, "_conversation_agent", ConversationAgent(fake_llm))

    orchestrator = Orchestrator(AgentRegistry())
    result = await orchestrator.handle(
        "does he have a PhD", tenant_id=tenant_id, knowledge_base_id=kb_id
    )

    assert result.response == "No, he does not have a PhD mentioned."
    assert result.chunks == []
    sent_user_message = next(m for m in fake_llm.received_messages[0] if m.role == "user")
    assert "no relevant documents were found" in sent_user_message.content


@dataclass
class _TruthyKeySettings:
    """A minimal stand-in for config.settings with just the one field
    orchestrator.py actually reads (`settings.openai_api_key`) -- not a
    mock of the whole Settings model, matching this file's own
    established "real, narrow fake" convention."""

    openai_api_key: str = "sk-test-fake-key-for-orchestrator-branch-coverage"
