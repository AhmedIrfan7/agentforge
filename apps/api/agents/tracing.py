"""Per-agent execution tracing (roadmap step 153, AGENTS.md's "AGENT
OBSERVABILITY" section). Scoped tightly to exactly what the roadmap
step's own parenthetical asks for -- latency, tokens, status -- not the
full aspirational field list AGENTS.md's section names (retry count,
confidence, resource usage, future cost estimation, ...). None of those
have a real caller or meaning in this codebase yet: no agent retries,
no agent reports a confidence score, no cost model exists anywhere.
Adding fields for them now would be machinery with nothing real behind
it, the same "don't build it before there's something real to hold"
discipline this project has applied throughout (`llm/__init__.py`'s own
PROVIDERS registry waiting for step 152, `agents/registry.py` starting
empty at 139).

`traced_run` wraps one `Agent.run()` call and logs one structured
"agent_execution" event -- the same "wrap the real call site with one
structured log event" shape `agents/retriever.py`'s own `_log_retrieval`
already established at step 129 for retrieval specifically, generalized
here to any Agent via `logging_config.py`'s existing `get_logger`
convention. It's a plain function, not a decorator or a change to
`Agent.run()` itself -- `orchestrator.py`'s real per-agent call sites
(`_planning_node`, `_execute_node`) call it explicitly, the same way
`_log_retrieval` is called explicitly rather than injected via
inheritance or a metaclass.

Failures are traced too: `except Exception` here is deliberate and
safe -- it logs a failure trace and immediately re-raises unchanged
(never swallows), so tracing observes without altering control flow.
This is a generic wrapper around ANY agent's `run()` (which can raise
anything, from a skeleton's `NotImplementedError` to a concrete agent's
own domain errors), unlike `llm/openai.py`'s narrow, provider-specific
`except (httpx.HTTPError, ...)`, which maps known failure types to one
error class.

Tokens are real, not faked: `prompt_tokens`/`completion_tokens` stay
`None` unless the agent's output IS an `llm.base.LLMResponse` (150) --
the only shape in this codebase that actually carries real token
counts. No agent's `run()` implementation calls an LLM yet (144-148 are
still honest `NotImplementedError` skeletons; 142/149's real
implementations don't call one either), so every trace this step can
currently produce has both token fields `None` -- an honest reflection
of what's real today, not a placeholder pretending otherwise. The
`isinstance` check means tracing starts reporting real tokens
automatically once a real LLM-calling agent lands, with no change
needed here.

As of step 245, `traced_run` also PERSISTS each trace to a real
`AgentExecutionLog` row when a caller passes `tenant_id` -- the real
backend gap step 245's own "agent-performance dashboard" needed
(structlog events alone give the dashboard nothing to query). Optional
and additive, not a breaking change: every existing call site
(agents/parallel.py, agents/resilience.py, this module's own tests)
keeps working unchanged by simply not passing it, since only
orchestrator.py's real per-request nodes (`_planning_node`,
`_execute_node`) have a genuine tenant_id in scope to give it.
Persistence uses its own short-lived `get_worker_session()` (the same
per-call pattern `orchestrator.py:_RetrieverGraphAgent` already
established), wrapped in its own `except Exception` that logs and
swallows rather than propagating -- the same "tracing observes without
altering control flow" principle this file's own logging path already
follows, applied to the new persistence path: a transient DB hiccup
while tracing must never turn into a broken chat turn for a real user.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Literal

from agents.base import Agent
from db import get_worker_session, set_tenant_context
from llm.base import LLMResponse
from logging_config import get_logger
from models.agent_execution_log import AgentExecutionLog

logger = get_logger(__name__)


@dataclass(frozen=True)
class AgentExecutionTrace:
    agent_name: str
    status: Literal["success", "failure"]
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None


def _log_trace(trace: AgentExecutionTrace) -> None:
    logger.info(
        "agent_execution",
        agent_name=trace.agent_name,
        status=trace.status,
        latency_ms=round(trace.latency_ms, 2),
        prompt_tokens=trace.prompt_tokens,
        completion_tokens=trace.completion_tokens,
    )


async def _persist_trace(trace: AgentExecutionTrace, tenant_id: uuid.UUID) -> None:
    try:
        async with get_worker_session() as session:
            await set_tenant_context(session, tenant_id)
            session.add(
                AgentExecutionLog(
                    tenant_id=tenant_id,
                    agent_name=trace.agent_name,
                    status=trace.status,
                    latency_ms=trace.latency_ms,
                )
            )
            await session.commit()
    except Exception:
        logger.exception("agent_execution_trace_persist_failed", agent_name=trace.agent_name)


async def traced_run[InputT, OutputT](
    agent: Agent[InputT, OutputT], input: InputT, *, tenant_id: uuid.UUID | None = None
) -> OutputT:
    start = time.perf_counter()
    try:
        output = await agent.run(input)
    except Exception:
        trace = AgentExecutionTrace(
            agent_name=agent.name,
            status="failure",
            latency_ms=(time.perf_counter() - start) * 1000,
            prompt_tokens=None,
            completion_tokens=None,
        )
        _log_trace(trace)
        if tenant_id is not None:
            await _persist_trace(trace, tenant_id)
        raise

    trace = AgentExecutionTrace(
        agent_name=agent.name,
        status="success",
        latency_ms=(time.perf_counter() - start) * 1000,
        prompt_tokens=output.prompt_tokens if isinstance(output, LLMResponse) else None,
        completion_tokens=(output.completion_tokens if isinstance(output, LLMResponse) else None),
    )
    _log_trace(trace)
    if tenant_id is not None:
        await _persist_trace(trace, tenant_id)
    return output
