"""Tests for agents/conversation.py (roadmap step 145) -- proves the
agent is real and constructible, and honestly reports as
not-yet-implemented rather than silently pretending to work."""

import pytest

from agents.base import Agent
from agents.conversation import ConversationAgent
from agents.registry import AgentRegistry


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = ConversationAgent()
    assert agent.name == "conversation"


def test_run_is_not_overridden_yet() -> None:
    assert type(ConversationAgent()).run is Agent.run


@pytest.mark.anyio
async def test_calling_run_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await ConversationAgent().run("anything")


def test_registering_it_reports_as_unhealthy() -> None:
    registry = AgentRegistry()
    registry.register(ConversationAgent())

    assert registry.discover() == ["conversation"]
    assert registry.health_check() == {"conversation": False}
