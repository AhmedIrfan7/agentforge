"""Tests for agents/quality_review.py (roadmap step 147) -- proves the
agent is real and constructible, and honestly reports as
not-yet-implemented rather than silently pretending to work."""

import pytest

from agents.base import Agent
from agents.quality_review import QualityReviewAgent
from agents.registry import AgentRegistry


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = QualityReviewAgent()
    assert agent.name == "quality_review"


def test_run_is_not_overridden_yet() -> None:
    assert type(QualityReviewAgent()).run is Agent.run


@pytest.mark.anyio
async def test_calling_run_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await QualityReviewAgent().run("anything")


def test_registering_it_reports_as_unhealthy() -> None:
    registry = AgentRegistry()
    registry.register(QualityReviewAgent())

    assert registry.discover() == ["quality_review"]
    assert registry.health_check() == {"quality_review": False}
