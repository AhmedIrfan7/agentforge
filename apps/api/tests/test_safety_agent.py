"""Tests for agents/safety.py (roadmap step 148) -- proves the agent
is real and constructible, and honestly reports as not-yet-implemented
rather than silently pretending to work (a fake "safe" verdict here
would be actively dangerous, not just dishonest)."""

import pytest

from agents.base import Agent
from agents.registry import AgentRegistry
from agents.safety import SafetyAgent


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = SafetyAgent()
    assert agent.name == "safety"


def test_run_is_not_overridden_yet() -> None:
    assert type(SafetyAgent()).run is Agent.run


@pytest.mark.anyio
async def test_calling_run_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await SafetyAgent().run("anything")


def test_registering_it_reports_as_unhealthy() -> None:
    registry = AgentRegistry()
    registry.register(SafetyAgent())

    assert registry.discover() == ["safety"]
    assert registry.health_check() == {"safety": False}
