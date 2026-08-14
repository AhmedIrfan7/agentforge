"""Tests for agents/reasoning.py (roadmap step 146) -- proves the
agent is real and constructible, and honestly reports as
not-yet-implemented rather than silently pretending to work."""

import pytest

from agents.base import Agent
from agents.reasoning import ReasoningAgent
from agents.registry import AgentRegistry


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = ReasoningAgent()
    assert agent.name == "reasoning"


def test_run_is_not_overridden_yet() -> None:
    assert type(ReasoningAgent()).run is Agent.run


@pytest.mark.anyio
async def test_calling_run_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await ReasoningAgent().run("anything")


def test_registering_it_reports_as_unhealthy() -> None:
    registry = AgentRegistry()
    registry.register(ReasoningAgent())

    assert registry.discover() == ["reasoning"]
    assert registry.health_check() == {"reasoning": False}
