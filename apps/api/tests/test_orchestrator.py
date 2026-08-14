"""Tests for orchestrator.py (roadmap steps 140-141) -- proves the real
LangGraph plumbing behind Orchestrator.handle() actually works end to
end, that it's a genuine service holding a real AgentRegistry
dependency (not a bare function), and that the real intent-analysis
node (141) correctly sets internal graph state.
"""

import pytest

from agents.registry import AgentRegistry
from orchestrator import Orchestrator, _classify_intent


@pytest.mark.anyio
async def test_handle_returns_the_query_via_the_real_graph() -> None:
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator.handle("hello")

    assert result == "hello"


def test_orchestrator_holds_the_registry_it_was_constructed_with() -> None:
    registry = AgentRegistry()
    orchestrator = Orchestrator(registry)

    assert orchestrator._registry is registry


@pytest.mark.anyio
async def test_each_orchestrator_instance_builds_its_own_independent_graph() -> None:
    first = Orchestrator(AgentRegistry())
    second = Orchestrator(AgentRegistry())

    assert first._graph is not second._graph
    assert await first.handle("a") == "a"
    assert await second.handle("b") == "b"


def test_classify_intent_recognizes_a_real_query_as_document_search() -> None:
    assert _classify_intent("find the refund policy") == "document_search"


def test_classify_intent_recognizes_an_empty_query() -> None:
    assert _classify_intent("") == "empty"


def test_classify_intent_recognizes_a_whitespace_only_query_as_empty() -> None:
    assert _classify_intent("   \n\t  ") == "empty"


@pytest.mark.anyio
async def test_the_graph_sets_document_search_intent_for_a_real_query() -> None:
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator._graph.ainvoke(
        {"query": "find the refund policy", "intent": "", "response": ""}
    )

    assert result["intent"] == "document_search"


@pytest.mark.anyio
async def test_the_graph_sets_empty_intent_for_a_blank_query() -> None:
    orchestrator = Orchestrator(AgentRegistry())

    result = await orchestrator._graph.ainvoke({"query": "   ", "intent": "", "response": ""})

    assert result["intent"] == "empty"
