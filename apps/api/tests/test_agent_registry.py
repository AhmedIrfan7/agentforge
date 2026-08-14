"""Tests for agents/registry.py (roadmap step 139) -- proves the real
register/discover/health-check behavior using real fake agents (not
mocks), same reasoning every other provider fake in this project
already uses.
"""

import pytest

from agents.base import Agent
from agents.registry import AgentAlreadyRegisteredError, AgentNotFoundError, AgentRegistry


class _WorkingAgent(Agent[str, str]):
    name = "working"

    async def run(self, input: str) -> str:
        return f"processed: {input}"


class _UnimplementedAgent(Agent[str, str]):
    name = "unimplemented"


def test_register_then_get_returns_the_same_agent() -> None:
    registry = AgentRegistry()
    agent = _WorkingAgent()

    registry.register(agent)

    assert registry.get("working") is agent


def test_registering_a_duplicate_name_raises() -> None:
    registry = AgentRegistry()
    registry.register(_WorkingAgent())

    with pytest.raises(AgentAlreadyRegisteredError):
        registry.register(_WorkingAgent())


def test_getting_an_unregistered_name_raises() -> None:
    registry = AgentRegistry()

    with pytest.raises(AgentNotFoundError):
        registry.get("nonexistent")


def test_discover_lists_registered_agent_names_sorted() -> None:
    registry = AgentRegistry()
    registry.register(_WorkingAgent())
    registry.register(_UnimplementedAgent())

    assert registry.discover() == ["unimplemented", "working"]


def test_discover_on_an_empty_registry_returns_an_empty_list() -> None:
    assert AgentRegistry().discover() == []


def test_health_check_reports_true_for_an_agent_with_a_real_run_override() -> None:
    registry = AgentRegistry()
    registry.register(_WorkingAgent())

    assert registry.health_check() == {"working": True}


def test_health_check_reports_false_for_an_agent_that_never_overrode_run() -> None:
    registry = AgentRegistry()
    registry.register(_UnimplementedAgent())

    assert registry.health_check() == {"unimplemented": False}


@pytest.mark.anyio
async def test_a_healthy_registered_agent_actually_runs() -> None:
    registry = AgentRegistry()
    registry.register(_WorkingAgent())

    agent = registry.get("working")
    result = await agent.run("hello")

    assert result == "processed: hello"
