"""Orchestrator service skeleton (roadmap step 140, AGENTS.md SECTION
5) -- the real service that will coordinate agent execution via a real
LangGraph graph, wired up incrementally by later, real steps: intent
analysis (141), a Planning Agent choosing which agents run and in what
order (142), and the first real agent wired in (143, Retriever Agent).

Deliberately minimal at this step -- same "skeleton now, real logic
layered in by later steps" shape steps 095/097 (Document Analysis/
Chunking Recommendation Agent skeletons) and agent_graph.py (137)
itself already established. `OrchestratorState` carries only `query`/
`response` today -- adding intent/plan/agent-result fields now, before
141/142 exist to define their own real shape, would be exactly the
kind of speculative guess this project's own "add the field when the
step that needs it lands" discipline (`SearchFilters` at 123, etc.)
argues against.

The one real node (`_echo_node`) is an honest placeholder, not real
orchestration -- its job is proving `Orchestrator.handle()` -> a real
`StateGraph` -> `ainvoke()` -> a real response actually works end to
end as a SERVICE (constructed with a real `AgentRegistry` dependency,
even though nothing in this graph queries it yet), the same "prove the
plumbing, not fake the logic" reasoning `agent_graph.py`'s own
passthrough node already used. `Orchestrator` builds its own real
graph in `__init__` rather than reusing `agent_graph.py`'s scaffold --
that scaffold's own job was proving LangGraph works in this codebase
at all (step 137, done); the Orchestrator is a distinct, higher-level
concept (a service holding a registry, exposing a real entry point),
not a second consumer of the exact same throwaway passthrough graph.
"""

from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.registry import AgentRegistry


class OrchestratorState(TypedDict):
    query: str
    response: str


async def _echo_node(state: OrchestratorState) -> dict[str, str]:
    return {"response": state["query"]}


class Orchestrator:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry
        self._graph = self._build_graph()

    def _build_graph(
        self,
    ) -> CompiledStateGraph[OrchestratorState, None, OrchestratorState, OrchestratorState]:
        builder = StateGraph(OrchestratorState)
        builder.add_node("echo", _echo_node)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)
        return builder.compile()

    async def handle(self, query: str) -> str:
        # ainvoke() is typed `dict[str, Any] | Any` by LangGraph itself
        # (verified live) -- cast() narrows the real, known-at-runtime
        # shape back to OrchestratorState (matching _build_graph()'s
        # own state schema) rather than letting Any leak into handle()'s
        # own real str return type.
        raw_result = await self._graph.ainvoke({"query": query, "response": ""})
        result = cast(OrchestratorState, raw_result)
        return result["response"]
