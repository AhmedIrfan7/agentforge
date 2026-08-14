"""Orchestrator service skeleton (roadmap step 140, AGENTS.md SECTION
5) -- the real service that will coordinate agent execution via a real
LangGraph graph, wired up incrementally by later, real steps: intent
analysis (141), a Planning Agent choosing which agents run and in what
order (142), and the first real agent wired in (143, Retriever Agent).

Deliberately minimal at step 140 -- same "skeleton now, real logic
layered in by later steps" shape steps 095/097 (Document Analysis/
Chunking Recommendation Agent skeletons) and agent_graph.py (137)
itself already established. `Orchestrator` builds its own real graph
in `__init__` rather than reusing `agent_graph.py`'s scaffold -- that
scaffold's own job was proving LangGraph works in this codebase at all
(step 137, done); the Orchestrator is a distinct, higher-level concept
(a service holding a registry, exposing a real entry point), not a
second consumer of the exact same throwaway passthrough graph.

As of step 141, `_classify_intent`/`_intent_analysis_node` add the
first real graph node, scoped tightly to what this codebase can
ACTUALLY act on today: AGENTS.md's own "INTENT ANALYSIS" section lists
ten example categories (question answering, document search,
conversation continuation, voice interaction, workflow execution,
memory retrieval, knowledge update, document upload, analytics
request, administrative task) -- but only "document search" has a real
subsystem behind it right now (RetrieverAgent, steps 120-134;
conversation/memory/voice/workflows/analytics/admin are all later,
unbuilt milestones). Building a ten-way classifier today, with nine
categories nothing can route to, would be dishonest scaffolding
pretending to more capability than exists. `document_search` vs.
`empty` is the one real, checkable distinction available: a genuinely
blank/whitespace-only query is never actionable regardless of what
gets built later, and everything else is -- today -- routed the same
one real way this system knows how to handle a query. `intent` stays
internal graph state, not part of `handle()`'s own external `str`
contract -- nothing outside the graph consumes it yet; step 142's
Planning Agent is the real, first consumer.

As of step 142, `_planning_node` calls `agents/planning.py:
PlanningAgent` for real, storing its `Plan.agent_names` into a new
`agent_names` state field -- a genuine, justified addition now that
planning actually produces it (same "add the field when the step that
needs it lands" discipline the rest of this state schema already
follows). `agent_names` currently names an agent nothing can execute
yet (`agents/registry.py:AgentRegistry` has nothing real registered --
step 143's own job); deciding what SHOULD run and being able to
actually run it are two different, deliberately separate concerns.
`_echo_node` doesn't read `agent_names` yet -- it stays the same
placeholder until 143 gives it something real to call.
"""

from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.planning import PlanningAgent
from agents.registry import AgentRegistry

_planning_agent = PlanningAgent()


class OrchestratorState(TypedDict):
    query: str
    intent: str
    agent_names: list[str]
    response: str


def _classify_intent(query: str) -> str:
    if not query.strip():
        return "empty"
    return "document_search"


async def _intent_analysis_node(state: OrchestratorState) -> dict[str, str]:
    return {"intent": _classify_intent(state["query"])}


async def _planning_node(state: OrchestratorState) -> dict[str, list[str]]:
    plan = await _planning_agent.run(state["intent"])
    return {"agent_names": plan.agent_names}


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
        builder.add_node("intent_analysis", _intent_analysis_node)
        builder.add_node("planning", _planning_node)
        builder.add_node("echo", _echo_node)
        builder.add_edge(START, "intent_analysis")
        builder.add_edge("intent_analysis", "planning")
        builder.add_edge("planning", "echo")
        builder.add_edge("echo", END)
        return builder.compile()

    async def handle(self, query: str) -> str:
        # ainvoke() is typed `dict[str, Any] | Any` by LangGraph itself
        # (verified live) -- cast() narrows the real, known-at-runtime
        # shape back to OrchestratorState (matching _build_graph()'s
        # own state schema) rather than letting Any leak into handle()'s
        # own real str return type.
        raw_result = await self._graph.ainvoke(
            {"query": query, "intent": "", "agent_names": [], "response": ""}
        )
        result = cast(OrchestratorState, raw_result)
        return result["response"]
