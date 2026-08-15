"""Memory-observability logging (roadmap step 172, AGENTS.md's own
"MEMORY OBSERVABILITY" section: "Administrators should understand why
something became long-term memory."). Scoped tightly to exactly the
roadmap step's own parenthetical -- created/updated/ignored -- not
AGENTS.md's fuller list (deleted, confidence, importance score,
expiration, retrieval, compression, summarization). "Deleted" already
has real, dedicated coverage via step 170's audit log
(`audit.py:write_audit_log`) -- a different mechanism for a different
audience (compliance/security, not day-to-day operational visibility)
-- and the rest have no real caller or meaning of their own yet.

`log_memory_event` is a thin structlog wrapper, the same
"`logging_config.py`'s `get_logger`, one structured event per real
decision" pattern `agents/tracing.py:traced_run` (153) already
established -- one event name (`"memory_lifecycle"`) with an
`outcome` field distinguishing cases, not three separately-named
events, matching that module's own "one event name, a status field"
shape rather than `agent_execution_success`/`agent_execution_failure`.

Wired into `memory_summarization.py`'s (167) real retention-decision
call site -- the one place in this codebase that actually decides
whether a `Memory` row gets created, with a real reason already
computed by `agents/memory.py:MemoryAgent` (165). Both outcomes are
logged: a retained summary logs `"created"`, a rejected one logs
`"ignored"` -- each carrying the same real `reason` the decision
itself already produced, not a second independently invented
explanation.

`"updated"` is a real, callable outcome this function supports, but
nothing in this codebase calls it with that value yet -- no code path
updates an existing `Memory` row today; step 173's own "memory
conflict-resolution logic" is the step that will need it, once
resolving a conflict means updating rather than creating a duplicate.
Same "field/capability exists, not every value is reachable by real
code yet" honesty `models/memory.py:memory_type`'s own `"short_term"`
value already established at step 162.
"""

from typing import Literal

from logging_config import get_logger

logger = get_logger(__name__)

MemoryOutcome = Literal["created", "updated", "ignored"]


def log_memory_event(
    outcome: MemoryOutcome,
    *,
    scope: str,
    reason: str,
    importance_score: float | None = None,
) -> None:
    logger.info(
        "memory_lifecycle",
        outcome=outcome,
        scope=scope,
        reason=reason,
        importance_score=importance_score,
    )
