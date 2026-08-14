"""Parallel execution for independent agent steps (roadmap step 154,
AGENTS.md's own "PARALLEL EXECUTION" section: "Determine where agents
can safely execute in parallel... Retrieval. Memory lookup. Analytics
logging. Context preparation.").

`run_parallel` is real, generic, tested infrastructure shipped ahead of
its first real production caller -- the same precedent this project
already established for `agents/registry.py:AgentRegistry` (139,
started empty), `orchestrator.py:Orchestrator._registry` (143, "real
infrastructure waiting for a genuinely stateless agent... to actually
need it"), and `llm/__init__.py:PROVIDERS` (152). `orchestrator.py`'s
`agent_names` plan can only ever be `["retriever"]` or `[]` today
(`agents/planning.py:PlanningAgent` has exactly one real branch) -- no
production request yet has two genuinely independent real agents to
run side by side, so `orchestrator.py` is deliberately NOT changed by
this step. Wiring a single-item list through `run_parallel` would be a
no-op that only adds indirection; wiring in a second, currently-
skeleton agent (e.g. `MemoryAgent`, which still raises
`NotImplementedError`) to manufacture a "real" second branch would
break every real document-search request today -- neither is honest.
This ships the capability, verified with real independent fake agents,
for the day `PlanningAgent` genuinely plans more than one.

Deliberately does NOT infer a dependency graph or decide what's safe to
parallelize -- AGENTS.md's own "without increasing inconsistency"
warning means that call is a caller's responsibility, the same
"caller supplies the correctly-scoped input, no fake generality"
discipline `agents/retriever.py:search_multi_query`'s caller-supplied
search closure already established at step 130.
`agents/citation.py:CitationAgent` is this codebase's one concrete
example of a real agent that is NOT a valid candidate here -- it needs
a prior retrieval's own output as its input, so it is never
independent of it.

Each step still runs through `agents/tracing.py:traced_run` (153), not
a bare `agent.run()` -- tracing must keep reporting per-agent
status/latency/tokens whether agents run sequentially or concurrently.
Uses `asyncio.gather`'s default (not `return_exceptions=True`): a
failure in any one step fails the whole batch immediately, matching
`asyncio.gather`'s ordinary semantics -- partial-result degradation on
failure is explicitly step 155's job, not this one's.
"""

import asyncio
from typing import Any

from agents.base import Agent
from agents.tracing import traced_run


async def run_parallel(steps: list[tuple[Agent[Any, Any], Any]]) -> list[Any]:
    return list(await asyncio.gather(*(traced_run(agent, input) for agent, input in steps)))
