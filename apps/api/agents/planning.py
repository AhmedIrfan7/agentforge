"""Planning Agent (roadmap step 142, AGENTS.md SECTION "PLANNING
AGENT" -- "determine what work needs to be done, which agents are
required, whether execution should happen sequentially or in
parallel, whether additional clarification is required, how
confidence should be measured").

Scoped to what's actually determinable today: `document_search`
(step 141's own intent-analysis node) is still the only real intent
this codebase has any agent for (`RetrieverAgent`) -- so `Plan` is
just `agent_names: list[str]`, either `["retriever"]` or `[]`. AGENTS.
md's other four determinations (sequential vs. parallel, clarification,
confidence) are all meaningless with only ever zero or one real
candidate agent in play: there's nothing to sequence, nothing to be
uncertain about, and no second option to need clarification between.
Adding those fields now, before a real second agent or a real
ambiguous case exists to justify them, would be exactly the kind of
speculative scaffolding this project has repeatedly rejected
(`vectorstore/base.py:SearchFilters`'s own deferred metadata-filtering
field, `citations.py:Citation`'s deliberately absent `page` field).

The first real implementation of `agents/base.py:Agent.run()` (step
138) in this codebase -- `DocumentAnalysisAgent`/`ChunkingRecommendation
Agent`/`RetrieverAgent` all stayed `Agent[Any, Any]`, since none of
them needed the graph-invocation contract for their own real callers.
`PlanningAgent` genuinely does: it exists specifically to be called
from `orchestrator.py`'s own graph (step 142's own second half), so
implementing `run()` for real -- not leaving it `NotImplementedError`
-- is the whole point.

`"retriever"` is a plain string naming the agent this plan wants, not
a lookup against `agents/registry.py:AgentRegistry` -- nothing has
registered a real, `run()`-implementing retriever agent there yet
(step 143's own job); planning what SHOULD happen and being able to
actually EXECUTE it are two different, separately-staged concerns.
"""

from dataclasses import dataclass, field

from agents.base import Agent


@dataclass(frozen=True)
class Plan:
    agent_names: list[str] = field(default_factory=list)


class PlanningAgent(Agent[str, Plan]):
    name = "planning"

    async def run(self, input: str) -> Plan:
        if input == "document_search":
            return Plan(agent_names=["retriever"])
        return Plan()
