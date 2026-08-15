"""Tests for agents/memory.py (roadmap step 165)."""

import pytest

from agents.memory import RETENTION_THRESHOLD, MemoryAgent, RetentionDecision
from llm.base import Message


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = MemoryAgent()
    assert agent.name == "memory"


@pytest.mark.anyio
async def test_short_content_is_not_retained() -> None:
    agent = MemoryAgent()

    decision = await agent.run(Message(role="user", content="ok thanks"))

    assert decision.should_retain is False
    assert decision.importance_score < RETENTION_THRESHOLD


@pytest.mark.anyio
async def test_content_with_an_identity_signal_is_retained_with_high_importance() -> None:
    agent = MemoryAgent()

    decision = await agent.run(
        Message(role="user", content="My name is Jordan and I prefer email over chat.")
    )

    assert decision.should_retain is True
    assert decision.importance_score == 0.9


@pytest.mark.anyio
async def test_identity_signal_detection_is_case_insensitive() -> None:
    agent = MemoryAgent()

    decision = await agent.run(Message(role="user", content="Please Remember that I work in EU."))

    assert decision.should_retain is True


@pytest.mark.anyio
async def test_substantive_content_with_no_signal_is_not_confidently_retained() -> None:
    agent = MemoryAgent()

    decision = await agent.run(
        Message(role="assistant", content="Our standard shipping takes five to seven days.")
    )

    assert decision.should_retain is False
    assert 0.1 < decision.importance_score < RETENTION_THRESHOLD


@pytest.mark.anyio
async def test_decision_always_includes_a_real_reason() -> None:
    agent = MemoryAgent()

    decision = await agent.run(Message(role="user", content="hi"))

    assert isinstance(decision, RetentionDecision)
    assert decision.reason != ""
