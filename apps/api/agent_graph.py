"""Base agent-graph scaffold (roadmap step 137, AGENTS.md SECTION 5) --
adds LangGraph as the real orchestration-graph library Milestone 4
builds on. The installed version (1.2.11) is a major-version jump past
any LangGraph release in this codebase's own training-era assumptions
-- its `StateGraph`/`compile`/`ainvoke` API was verified live before
writing anything here (a throwaway probe script, since deleted, built
a real minimal graph and ran it end to end), not trusted from memory,
same "verify any new library API live before trusting it" discipline
this project has used for every other new dependency (pgvector,
tiktoken, structlog's `capture_logs`, etc.).

This is deliberately a bare scaffold, not real orchestration logic --
the same "minimal, honest placeholder now, real logic added by later,
real steps" shape `agents/base.py`'s own original `Agent` class had
(just a `name` attribute) before steps 095-124 built real agents on
top of it. `GraphState` is a minimal, generic input/output shape, not
yet this project's own Agent-shaped node contract (that's step 138).
`build_base_graph()`'s one node is an honest identity passthrough --
its only job is proving `StateGraph` -> `add_node` -> `add_edge` ->
`compile` -> `ainvoke` actually works end to end in this codebase's
real async runtime, nothing more. Steps 138-143 (Agent base class,
Agent Registry, Orchestrator skeleton, Planning Agent, wiring
RetrieverAgent in) are where real nodes replace this passthrough.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class GraphState(TypedDict):
    input: str
    output: str


async def _passthrough_node(state: GraphState) -> dict[str, str]:
    return {"output": state["input"]}


def build_base_graph() -> CompiledStateGraph[GraphState, None, GraphState, GraphState]:
    builder = StateGraph(GraphState)
    builder.add_node("passthrough", _passthrough_node)
    builder.add_edge(START, "passthrough")
    builder.add_edge("passthrough", END)
    return builder.compile()
