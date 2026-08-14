"""Tests for agents/parallel.py (roadmap step 154). The real payoff to
prove is genuine concurrency, not just "calls each agent and collects
results" -- test_run_parallel_actually_runs_concurrently_not_sequentially
uses real asyncio.sleep() delays and wall-clock timing to distinguish
run_parallel from a sequential loop that would happen to produce the
same return value.
"""

import asyncio
import time
from collections.abc import MutableMapping
from typing import Any

import pytest
import structlog.testing

from agents.base import Agent
from agents.parallel import run_parallel


class _DelayedEchoAgent(Agent[str, str]):
    def __init__(self, name: str, delay_seconds: float) -> None:
        self.name = name
        self._delay_seconds = delay_seconds

    async def run(self, input: str) -> str:
        await asyncio.sleep(self._delay_seconds)
        return f"{self.name}: {input}"


class _FailingAgent(Agent[str, str]):
    name = "failing"

    async def run(self, input: str) -> str:
        raise ValueError("boom")


def _events(logs: list[MutableMapping[str, Any]]) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == "agent_execution"]


@pytest.mark.anyio
async def test_run_parallel_returns_each_agents_real_output_in_order() -> None:
    results = await run_parallel(
        [
            (_DelayedEchoAgent("first", 0), "a"),
            (_DelayedEchoAgent("second", 0), "b"),
        ]
    )

    assert results == ["first: a", "second: b"]


@pytest.mark.anyio
async def test_run_parallel_actually_runs_concurrently_not_sequentially() -> None:
    steps: list[tuple[Agent[Any, Any], Any]] = [
        (_DelayedEchoAgent(f"agent-{i}", 0.2), "input") for i in range(3)
    ]

    start = time.perf_counter()
    await run_parallel(steps)
    elapsed = time.perf_counter() - start

    # Sequential would take >= 0.6s (3 * 0.2s); concurrent stays close to 0.2s.
    assert elapsed < 0.4


@pytest.mark.anyio
async def test_run_parallel_traces_every_step_independently() -> None:
    with structlog.testing.capture_logs() as logs:
        await run_parallel(
            [
                (_DelayedEchoAgent("first", 0), "a"),
                (_DelayedEchoAgent("second", 0), "b"),
            ]
        )

    events = _events(logs)
    assert {e["agent_name"] for e in events} == {"first", "second"}
    assert all(e["status"] == "success" for e in events)


@pytest.mark.anyio
async def test_run_parallel_propagates_a_failure_from_any_step() -> None:
    with pytest.raises(ValueError, match="boom"):
        await run_parallel(
            [
                (_DelayedEchoAgent("first", 0.05), "a"),
                (_FailingAgent(), "b"),
            ]
        )
