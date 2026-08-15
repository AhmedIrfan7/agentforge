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
no-op that only adds indirection; wiring in a second, still-skeleton
agent (e.g. `ConversationAgent`, which still raises
`NotImplementedError`) to manufacture a "real" second branch would
break every real document-search request today -- neither is honest.
(`MemoryAgent` gained real logic at step 165, but its `run()` is a
pure decision function with no repository/session dependency to
combine with `retriever`'s own request-scoped inputs here.)
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
`run_parallel` uses `asyncio.gather`'s default (not
`return_exceptions=True`): a failure in any one step fails the whole
batch immediately, matching `asyncio.gather`'s ordinary semantics --
the right choice when a caller genuinely needs every step to succeed.

As of step 155, `gather_partial` adds the other half AGENTS.md's own
"FAILURE HANDLING" section asks for -- "one failing agent should not
unnecessarily break the entire request" -- for callers that can
tolerate some steps failing. It's a distinct function, not a flag on
`run_parallel`, because the two have genuinely different return shapes
(`run_parallel` returns raw outputs; `gather_partial` returns one
`AgentStepResult` per step, `ok` or `failed`) -- a boolean flag would
force every caller to handle a shape it doesn't need. `agents/
resilience.py:with_retry`/`with_fallback` (155) cover the other two
items in step 155's own parenthetical (retry, fallback); they live in
their own module since they're about a single agent call, not a batch.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from agents.base import Agent
from agents.tracing import traced_run


async def run_parallel(steps: list[tuple[Agent[Any, Any], Any]]) -> list[Any]:
    return list(await asyncio.gather(*(traced_run(agent, input) for agent, input in steps)))


@dataclass(frozen=True)
class AgentStepResult:
    agent_name: str
    status: Literal["ok", "failed"]
    output: Any = None
    error: str | None = None


async def gather_partial(steps: list[tuple[Agent[Any, Any], Any]]) -> list[AgentStepResult]:
    raw_results = await asyncio.gather(
        *(traced_run(agent, input) for agent, input in steps), return_exceptions=True
    )
    results: list[AgentStepResult] = []
    for (agent, _input), raw in zip(steps, raw_results, strict=True):
        if isinstance(raw, BaseException):
            results.append(AgentStepResult(agent_name=agent.name, status="failed", error=str(raw)))
        else:
            results.append(AgentStepResult(agent_name=agent.name, status="ok", output=raw))
    return results
