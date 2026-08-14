"""Tests for agents/memory.py (roadmap step 144) -- proves the agent
is real and constructible, and honestly reports as not-yet-implemented
rather than silently pretending to work."""

import pytest

from agents.base import Agent
from agents.memory import MemoryAgent
from agents.registry import AgentRegistry


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = MemoryAgent()
    assert agent.name == "memory"


def test_run_is_not_overridden_yet() -> None:
    """A genuine skeleton, not a stub -- no Memory model/migration
    exists yet (Milestone 5), so run() staying agents/base.py's own
    NotImplementedError default is the honest state, not a bug."""
    assert type(MemoryAgent()).run is Agent.run


@pytest.mark.anyio
async def test_calling_run_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await MemoryAgent().run("anything")


def test_registering_it_reports_as_unhealthy() -> None:
    """The real, intended payoff of AgentRegistry.health_check()'s own
    design (step 139): a skeleton agent can be registered and
    discovered without dishonestly claiming to be ready."""
    registry = AgentRegistry()
    registry.register(MemoryAgent())

    assert registry.discover() == ["memory"]
    assert registry.health_check() == {"memory": False}
