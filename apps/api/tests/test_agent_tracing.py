"""Tests for agents/tracing.py (roadmap step 153). Same
structlog.testing.capture_logs() technique test_retriever_agent.py
already established at step 129 for asserting real structured log
events, generalized here to traced_run's "agent_execution" event.
"""

from collections.abc import MutableMapping
from typing import Any

import pytest
import structlog.testing

from agents.base import Agent
from agents.tracing import traced_run
from llm.base import LLMResponse


class _EchoAgent(Agent[str, str]):
    name = "echo"

    async def run(self, input: str) -> str:
        return f"echo: {input}"


class _FailingAgent(Agent[str, str]):
    name = "failing"

    async def run(self, input: str) -> str:
        raise ValueError("boom")


class _LLMBackedAgent(Agent[str, LLMResponse]):
    name = "llm-backed"

    async def run(self, input: str) -> LLMResponse:
        return LLMResponse(content="hi", prompt_tokens=12, completion_tokens=3)


def _events(logs: list[MutableMapping[str, Any]]) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == "agent_execution"]


@pytest.mark.anyio
async def test_traced_run_returns_the_real_agent_output() -> None:
    result = await traced_run(_EchoAgent(), "hello")
    assert result == "echo: hello"


@pytest.mark.anyio
async def test_traced_run_logs_a_success_event_with_no_tokens() -> None:
    with structlog.testing.capture_logs() as logs:
        await traced_run(_EchoAgent(), "hello")

    events = _events(logs)
    assert len(events) == 1
    assert events[0]["agent_name"] == "echo"
    assert events[0]["status"] == "success"
    assert events[0]["latency_ms"] >= 0
    assert events[0]["prompt_tokens"] is None
    assert events[0]["completion_tokens"] is None


@pytest.mark.anyio
async def test_traced_run_logs_a_failure_event_and_reraises() -> None:
    with structlog.testing.capture_logs() as logs, pytest.raises(ValueError, match="boom"):
        await traced_run(_FailingAgent(), "hello")

    events = _events(logs)
    assert len(events) == 1
    assert events[0]["agent_name"] == "failing"
    assert events[0]["status"] == "failure"
    assert events[0]["prompt_tokens"] is None


@pytest.mark.anyio
async def test_traced_run_reports_real_tokens_for_an_llm_backed_agent() -> None:
    with structlog.testing.capture_logs() as logs:
        await traced_run(_LLMBackedAgent(), "hello")

    events = _events(logs)
    assert events[0]["prompt_tokens"] == 12
    assert events[0]["completion_tokens"] == 3
