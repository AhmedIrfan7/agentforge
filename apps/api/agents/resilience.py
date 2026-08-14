"""Agent failure handling: retry and fallback (roadmap step 155,
AGENTS.md's own "FAILURE HANDLING" section: "One failing agent should
not unnecessarily break the entire request."). Scoped tightly to
exactly the roadmap step's own parenthetical -- retry, fallback,
partial-result degradation (the third lives in `agents/parallel.py:
gather_partial`, alongside `run_parallel` since both are about running
a batch of steps) -- not AGENTS.md's fuller aspirational list
(alternative strategy, human-readable errors, confidence reduction,
escalation). None of those have real meaning in this codebase yet: no
agent reports a confidence score at all (`agents/tracing.py`'s own
step-153 scoping already made this call), and "escalation" implies a
human-in-the-loop workflow nothing here builds. Same "scope tightly to
the roadmap's own words" discipline 153/154 already applied.

No retry library (tenacity/backoff) added as a dependency. This
project's existing retry precedent (`embeddings_pipeline.py`/
`extraction.py`, step 112) is Celery's own `autoretry_for`/
`retry_backoff`, which exists only for Celery *tasks* (background
jobs) -- agent execution runs inline inside a request/response cycle
with no Celery task wrapping it, so that mechanism doesn't apply here.
A small, explicit async loop is the honest equivalent for this
execution context, the same "raw approach over a library that buys
nothing extra for one small job" reasoning `llm/openai.py`/
`embeddings/openai.py` already used for HTTP calls instead of a vendor
SDK.

Both helpers wrap `agents/tracing.py:traced_run` (153), not a bare
`agent.run()` -- every attempt, including ones that fail and get
retried or replaced, still gets its own real tracing event, so an
operator can see exactly how many attempts a request actually took and
which agent finally produced the result.
"""

import asyncio

from agents.base import Agent
from agents.tracing import traced_run
from logging_config import get_logger

logger = get_logger(__name__)


async def with_retry[InputT, OutputT](
    agent: Agent[InputT, OutputT],
    input: InputT,
    *,
    max_attempts: int = 3,
    backoff_seconds: float = 0.1,
) -> OutputT:
    # All attempts but the last are caught and retried with a linearly
    # growing backoff; the final attempt is unguarded, so a real,
    # final failure raises the agent's own real exception rather than
    # a wrapper -- a caller inspecting the error sees exactly what the
    # agent itself raised.
    for attempt in range(1, max_attempts):
        try:
            return await traced_run(agent, input)
        except Exception:
            logger.warning(
                "agent_retry", agent_name=agent.name, attempt=attempt, max_attempts=max_attempts
            )
            await asyncio.sleep(backoff_seconds * attempt)
    return await traced_run(agent, input)


async def with_fallback[InputT, OutputT](
    primary: Agent[InputT, OutputT],
    fallback: Agent[InputT, OutputT],
    input: InputT,
) -> OutputT:
    try:
        return await traced_run(primary, input)
    except Exception:
        logger.warning("agent_fallback", primary=primary.name, fallback=fallback.name)
        return await traced_run(fallback, input)
