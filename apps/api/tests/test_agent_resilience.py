"""Tests for agents/resilience.py (roadmap step 155). Uses agents that
fail a fixed number of times before succeeding (a mutable counter on
the fake agent instance) to prove with_retry genuinely retries rather
than just happening to succeed on the first real call.
"""

import pytest

from agents.base import Agent
from agents.resilience import with_fallback, with_retry


class _FlakyAgent(Agent[str, str]):
    name = "flaky"

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self.call_count = 0

    async def run(self, input: str) -> str:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise ValueError(f"attempt {self.call_count} failed")
        return f"succeeded on attempt {self.call_count}: {input}"


class _AlwaysFailsAgent(Agent[str, str]):
    name = "always-fails"

    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, input: str) -> str:
        self.call_count += 1
        raise ValueError("always fails")


class _EchoAgent(Agent[str, str]):
    def __init__(self, name: str) -> None:
        self.name = name

    async def run(self, input: str) -> str:
        return f"{self.name}: {input}"


@pytest.mark.anyio
async def test_with_retry_succeeds_after_transient_failures() -> None:
    agent = _FlakyAgent(fail_times=2)

    result = await with_retry(agent, "hi", max_attempts=3, backoff_seconds=0)

    assert result == "succeeded on attempt 3: hi"
    assert agent.call_count == 3


@pytest.mark.anyio
async def test_with_retry_raises_the_real_error_after_exhausting_attempts() -> None:
    agent = _AlwaysFailsAgent()

    with pytest.raises(ValueError, match="always fails"):
        await with_retry(agent, "hi", max_attempts=3, backoff_seconds=0)

    assert agent.call_count == 3


@pytest.mark.anyio
async def test_with_retry_makes_exactly_one_call_when_max_attempts_is_one() -> None:
    agent = _AlwaysFailsAgent()

    with pytest.raises(ValueError):
        await with_retry(agent, "hi", max_attempts=1, backoff_seconds=0)

    assert agent.call_count == 1


@pytest.mark.anyio
async def test_with_fallback_uses_primary_result_when_primary_succeeds() -> None:
    result = await with_fallback(_EchoAgent("primary"), _EchoAgent("fallback"), "hi")

    assert result == "primary: hi"


@pytest.mark.anyio
async def test_with_fallback_uses_fallback_result_when_primary_fails() -> None:
    result = await with_fallback(_AlwaysFailsAgent(), _EchoAgent("fallback"), "hi")

    assert result == "fallback: hi"


@pytest.mark.anyio
async def test_with_fallback_raises_when_both_primary_and_fallback_fail() -> None:
    with pytest.raises(ValueError, match="always fails"):
        await with_fallback(_AlwaysFailsAgent(), _AlwaysFailsAgent(), "hi")
