"""Tests for orchestrator.py (roadmap step 140) -- proves the real
LangGraph plumbing behind Orchestrator.handle() actually works end to
end, and that it's a genuine service holding a real AgentRegistry
dependency, not a bare function.
"""

import pytest

from agents.registry import AgentRegistry
from orchestrator import Orchestrator


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
