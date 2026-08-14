"""Tests for agents/base.py:Agent (roadmap step 138) -- the real
run()/config contract, and that it stays honestly non-enforcing for
agents that don't implement run() (documented, not an abstractmethod).
"""

import pytest

from agents.base import Agent


class _FakeAgent(Agent[str, str]):
    """A real implementation of the run() contract -- not a mock of
    one -- same reasoning every other provider fake in this project
    already uses."""

    name = "fake"

    async def run(self, input: str) -> str:
        return f"processed: {input}"


def test_default_config_is_an_empty_dict() -> None:
    agent = Agent[str, str]()
    assert agent.config == {}


def test_config_is_stored_when_provided() -> None:
    agent = Agent[str, str](config={"model": "gpt-4"})
    assert agent.config == {"model": "gpt-4"}


@pytest.mark.anyio
async def test_base_run_is_not_implemented_by_default() -> None:
    """Documented convention, not an abstractmethod -- calling run()
    on an agent that never overrides it fails loudly rather than doing
    nothing, but instantiating one is never blocked."""
    agent = Agent[str, str]()
    with pytest.raises(NotImplementedError):
        await agent.run("anything")


@pytest.mark.anyio
async def test_a_real_subclass_overriding_run_works_end_to_end() -> None:
    agent = _FakeAgent()
    result = await agent.run("hello")
    assert result == "processed: hello"
