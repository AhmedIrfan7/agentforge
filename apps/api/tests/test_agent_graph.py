"""Tests for agent_graph.py (roadmap step 137) -- proves the real
LangGraph plumbing (StateGraph -> add_node -> add_edge -> compile ->
ainvoke) actually works in this codebase's real async runtime, not
just that the module imports without error.
"""

import pytest

from agent_graph import build_base_graph


@pytest.mark.anyio
async def test_the_compiled_graph_runs_the_passthrough_node() -> None:
    graph = build_base_graph()

    result = await graph.ainvoke({"input": "hello", "output": ""})

    assert result["output"] == "hello"


@pytest.mark.anyio
async def test_build_base_graph_returns_a_fresh_graph_each_call() -> None:
    """Not a shared, stateful singleton -- each call builds its own
    independent compiled graph."""
    first = build_base_graph()
    second = build_base_graph()

    assert first is not second
