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
`empty` is the one real, checkable distinction available.

As of step 142, `_planning_node` calls `agents/planning.py:
PlanningAgent` for real, storing its `Plan.agent_names` into a new
`agent_names` state field.

As of step 143, `_RetrieverGraphAgent`/`_execute_node` finally make
`agent_names` executable -- the "thin adapter wraps RetrieverAgent to
satisfy this interface for graph use specifically" step `agents/
base.py`'s own step-138 docstring already named. `OrchestratorState`
gains `tenant_id`/`knowledge_base_id`, a genuinely justified addition
now: real retrieval needs them, the same "add the field when the step
that needs it lands" discipline this state schema has followed since
141. `Orchestrator.handle()` grows matching keyword-only parameters
for the same real reason -- no HTTP caller exists yet to force a
particular shape, so this is the first, honest shape a real caller
(a future chat/conversation endpoint) will need.

As of step 153, `_planning_node`/`_execute_node` call their agents
through `agents/tracing.py:traced_run` rather than `.run()` directly --
these are the two real per-agent call sites this codebase has today,
matching AGENTS.md's own "END-TO-END EXECUTION TRACING" diagram
(Planning Agent, Selected Agents). See that module's own docstring for
why tokens stay honestly `None` for both today.

`_RetrieverGraphAgent` is deliberately NOT registered into `agents/
registry.py:AgentRegistry` -- that registry's whole design (step 139)
assumes stateless, construct-once, look-up-many agents, but this
adapter is genuinely request-scoped (`tenant_id`/`knowledge_base_id`
differ per call), which the registry's `register()` never accounted
for. Forcing a per-request object into an app-wide singleton registry
would be a worse fit than just constructing it fresh inside the node
that needs it, the same way `vectorstore/pgvector.py:PgVectorStore.
search()` opens its own `get_worker_session()` internally rather than
taking one injected -- both chose "no fixed caller yet" honesty over a
premature abstraction. `Orchestrator._registry` stays unused by this
step too; it's real infrastructure waiting for a genuinely stateless
agent (steps 144+) to actually need it.

Uses `ChunkRepository.search_by_keyword` specifically, not dense or
hybrid -- the one retrieval mechanism that works for real in every
environment, including this one with no OPENAI_API_KEY (same
documented gap dense/hybrid have had since step 107); a future step
can add real strategy selection once a real chat/generation caller
exists to justify it. The response for a real `document_search` hit is
the retrieved chunks' own raw text, not a synthesized answer -- no
chat/generation model exists yet (steps 150+) to produce one honestly;
surfacing the real retrieved content is the honest thing to return
today, not a faked summary.

As of step 187, `handle()` returns `OrchestratorResult` (`response`
+ `chunks: list[RetrievedChunk]`), not a bare `str` -- a real,
motivated widening of a signature this project has otherwise kept
deliberately narrow (step 179's own docstring explicitly declined to
add conversation history for the identical reason: don't extend ahead
of a step that actually needs it). Step 187 ("citation display in
chat responses") is that step: `routers/conversation.py` needs to know
WHICH chunks actually fed a response to build real `citations.py:
Citation` objects, and `chunks` is the one new field that makes that
possible without the orchestrator itself reaching into `citations.py`
or a DB session it doesn't otherwise need (document/knowledge-base
lookups stay the caller's job, matching that module's own "no DB
access of its own" design). `OrchestratorState` gained the matching
`chunks` field for the same reason `response`/`agent_names` etc. are
graph state -- every node that can produce chunks (today, only
`_execute_node`) sets it; every path sets it explicitly (`[]` for the
echo/no-results cases) rather than leaving it implicit, so `handle()`
never has to guess whether an omitted key means "none" or "not run
yet".
"""

import uuid
from dataclasses import dataclass
from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.base import Agent
from agents.planning import PlanningAgent
from agents.registry import AgentRegistry, agent_registry
from agents.retriever import RetrievedChunk, RetrieverAgent
from agents.tracing import traced_run
from db import get_worker_session, set_tenant_context
from embeddings.openai import OpenAIEmbeddingProvider
from repositories.chunk import ChunkRepository
from vectorstore.pgvector import PgVectorStore

_planning_agent = PlanningAgent()
_retriever_agent = RetrieverAgent(OpenAIEmbeddingProvider(), PgVectorStore())


class OrchestratorState(TypedDict):
    query: str
    tenant_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    intent: str
    agent_names: list[str]
    response: str
    chunks: list[RetrievedChunk]


def _classify_intent(query: str) -> str:
    if not query.strip():
        return "empty"
    return "document_search"


async def _intent_analysis_node(state: OrchestratorState) -> dict[str, str]:
    return {"intent": _classify_intent(state["query"])}


async def _planning_node(state: OrchestratorState) -> dict[str, list[str]]:
    plan = await traced_run(_planning_agent, state["intent"])
    return {"agent_names": plan.agent_names}


class _RetrieverGraphAgent(Agent[str, list[RetrievedChunk]]):
    name = "retriever"

    def __init__(self, tenant_id: uuid.UUID, knowledge_base_id: uuid.UUID) -> None:
        self._tenant_id = tenant_id
        self._knowledge_base_id = knowledge_base_id

    async def run(self, input: str) -> list[RetrievedChunk]:
        async with get_worker_session() as session:
            await set_tenant_context(session, self._tenant_id)
            repo = ChunkRepository(session, self._tenant_id)
            return await _retriever_agent.search_keyword(repo, self._knowledge_base_id, input)


async def _execute_node(state: OrchestratorState) -> dict[str, object]:
    if "retriever" not in state["agent_names"]:
        return {"response": state["query"], "chunks": []}

    agent = _RetrieverGraphAgent(state["tenant_id"], state["knowledge_base_id"])
    results = await traced_run(agent, state["query"])
    if not results:
        return {"response": "No results found.", "chunks": []}
    return {"response": "\n\n".join(r.text for r in results), "chunks": results}


@dataclass(frozen=True)
class OrchestratorResult:
    response: str
    chunks: list[RetrievedChunk]


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
        builder.add_node("execute", _execute_node)
        builder.add_edge(START, "intent_analysis")
        builder.add_edge("intent_analysis", "planning")
        builder.add_edge("planning", "execute")
        builder.add_edge("execute", END)
        return builder.compile()

    async def handle(
        self, query: str, *, tenant_id: uuid.UUID, knowledge_base_id: uuid.UUID
    ) -> OrchestratorResult:
        # ainvoke() is typed `dict[str, Any] | Any` by LangGraph itself
        # (verified live) -- cast() narrows the real, known-at-runtime
        # shape back to OrchestratorState (matching _build_graph()'s
        # own state schema) rather than letting Any leak into handle()'s
        # own real return type.
        raw_result = await self._graph.ainvoke(
            {
                "query": query,
                "tenant_id": tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "intent": "",
                "agent_names": [],
                "response": "",
                "chunks": [],
            }
        )
        result = cast(OrchestratorState, raw_result)
        return OrchestratorResult(response=result["response"], chunks=result["chunks"])


# Module-level singleton for real app-wide use (step 179's message-send
# endpoint is the first real caller) -- same shape agents/registry.py's
# own `agent_registry` singleton already established; tests construct
# their own fresh `Orchestrator(AgentRegistry())` instances instead, to
# avoid cross-test pollution of shared global state.
orchestrator = Orchestrator(agent_registry)
