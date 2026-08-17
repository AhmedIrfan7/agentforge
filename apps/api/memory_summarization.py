"""Memory-summarization background job (roadmap step 167, AGENTS.md's
own "MEMORY AGENT" section: "Memory summarization"). Same Celery task
shape `embeddings_pipeline.py:dispatch_embedding_generation` (108, 112)
already established: an async `_run_*` function doing the real work
via `get_worker_session()`, wrapped by a synchronous `@celery_app.task`
with `autoretry_for`/`retry_backoff` -- registered in `celery_app.py`'s
own `imports` tuple so the separate worker process actually sees it
(that file's own docstring already documents the real `KeyError` this
project hit once from forgetting that step).

This is the first task in this codebase to call a real LLM provider.
No agent calls one yet, but `llm/openai.py:OpenAIProvider` (151) is
real, tested, already-live-probed infrastructure sitting unused --
calling it directly here (not through an agent; summarization isn't
an `Agent.run()`-shaped decision the way `agents/memory.py:MemoryAgent`
retention scoring is) is exactly the same "real code, fails closed
without a key, documented environment gap" pattern
`embeddings_pipeline.py` already established for embedding generation
-- not new scaffolding, the established discipline applied to a new
call. `LLMProviderError` is deliberately NOT caught here: letting it
propagate lets Celery's own `autoretry_for` retry a real transient
failure, the same as every other external-API-calling task in this
codebase; this environment's missing `OPENAI_API_KEY` means every real
run here fails closed the same documented way embedding generation
does.

Reuses `agents/memory.py:MemoryAgent` (165) as the retention gate for
the summary itself -- "not every conversation should become permanent
memory" applies exactly as much to a generated summary as to a raw
turn, so the same real decision logic decides whether the summary
becomes a `Memory` row, not a second, independently invented rule.
`short_term_memory.clear()` (163) runs after a successful summarization
attempt either way (retained or not) -- the raw turns have been
processed once summarized; keeping them around risks re-summarizing
the same content on a later dispatch.

As of step 168, a retained summary's `expires_at` comes from
`memory_policy.py:compute_expiration`, fed the same `importance_score`
`MemoryAgent`'s own decision already computed -- one real policy
governs every `Memory` row this codebase writes, not a second,
independently invented expiration rule for summaries specifically.

As of step 172, both outcomes of the retention decision are logged via
`memory_observability.py:log_memory_event` -- a retained summary logs
`"created"`, a rejected one logs `"ignored"`, each carrying the same
real `decision.reason` `MemoryAgent` already computed. This is the one
real "create or not, with a reason" decision point in this codebase
today, so it's the honest, complete integration point for that step.

As of step 173, a retained summary is checked against this session's
own existing memories via `memory_conflict.py:find_conflicting_memory`
before writing -- a session summarized more than once could otherwise
accumulate near-duplicate summaries. A genuine conflict is resolved by
score: a new summary that meets or beats the conflicting memory's
`importance_score` replaces its content via `MemoryRepository.
update_content` (173's own reason that method exists) and logs
`"updated"`; one that doesn't beat it changes nothing and logs
`"ignored"` with a conflict-specific reason, distinct from
`MemoryAgent`'s own retention-threshold reasons. Only a genuine
`should_retain` summary is checked at all -- one already rejected by
`MemoryAgent` has no business being compared against existing memories
for a *different* reason to keep it.

As of step 251, every stored "assistant" turn is wrapped via
`agents/safety.py:SafetyAgent` before it reaches this real LLM call --
see that module's own docstring for why (a stored assistant turn IS raw
retrieved document text today, completely unmarked without this).
"""

import asyncio
import uuid
from typing import Any

from agents.memory import MemoryAgent
from agents.safety import SEPARATION_INSTRUCTION, ContentSeparationRequest, SafetyAgent
from agents.tracing import traced_run
from celery_app import celery_app
from db import get_worker_session, set_tenant_context
from llm.base import LLMProvider, Message
from llm.openai import OpenAIProvider
from memory_conflict import find_conflicting_memory
from memory_observability import log_memory_event
from memory_policy import compute_expiration
from repositories.memory import MemoryRepository
from short_term_memory import clear, get_recent_turns

_llm_provider: LLMProvider = OpenAIProvider()
_memory_agent = MemoryAgent()
_safety_agent = SafetyAgent()

_SUMMARIZATION_SYSTEM_PROMPT = (
    "Summarize the key facts, preferences, and important information "
    "from this conversation in two to three sentences. Focus on details "
    "worth remembering for future conversations.\n\n" + SEPARATION_INSTRUCTION
)


async def _wrap_assistant_turns(turns: list[Message], *, tenant_id: uuid.UUID) -> list[Message]:
    # As of step 251: each stored "assistant" turn IS raw retrieved
    # document text today (orchestrator.py's own _execute_node, no
    # chat/generation model exists yet to produce a synthesized reply
    # instead) -- see agents/safety.py's own docstring for the real
    # vulnerability wrapping it closes. User turns pass through
    # unchanged: AGENTS.md's own PROMPT INJECTION DEFENSE section is
    # about untrusted RETRIEVED content specifically, a distinct concern
    # from the user's own typed query.
    wrapped: list[Message] = []
    for turn in turns:
        if turn.role != "assistant":
            wrapped.append(turn)
            continue
        wrapped_content = await traced_run(
            _safety_agent, ContentSeparationRequest(content=turn.content), tenant_id=tenant_id
        )
        wrapped.append(Message(role="assistant", content=wrapped_content))
    return wrapped


async def _run_memory_summarization(session_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    turns = await get_recent_turns(session_id)
    if not turns:
        return

    wrapped_turns = await _wrap_assistant_turns(turns, tenant_id=tenant_id)
    messages = [Message(role="system", content=_SUMMARIZATION_SYSTEM_PROMPT), *wrapped_turns]
    response = await _llm_provider.complete(messages)

    decision = await _memory_agent.run(Message(role="assistant", content=response.content))
    if decision.should_retain:
        expires_at = compute_expiration(decision.importance_score)
        async with get_worker_session() as session:
            await set_tenant_context(session, tenant_id)
            repo = MemoryRepository(session, tenant_id)
            existing = await repo.list_for_session(session_id)
            conflict = find_conflicting_memory(existing, response.content)

            if conflict is not None and decision.importance_score < conflict.importance_score:
                await session.commit()
                log_memory_event(
                    "ignored",
                    scope="session",
                    reason="conflicts with an existing higher-importance memory",
                    importance_score=decision.importance_score,
                )
            elif conflict is not None:
                await repo.update_content(
                    conflict,
                    content=response.content,
                    importance_score=decision.importance_score,
                    expires_at=expires_at,
                )
                await session.commit()
                log_memory_event(
                    "updated",
                    scope="session",
                    reason="replaces a lower- or equal-importance conflicting memory",
                    importance_score=decision.importance_score,
                )
            else:
                await repo.create(
                    scope="session",
                    session_id=session_id,
                    content=response.content,
                    importance_score=decision.importance_score,
                    expires_at=expires_at,
                )
                await session.commit()
                log_memory_event(
                    "created",
                    scope="session",
                    reason=decision.reason,
                    importance_score=decision.importance_score,
                )
    else:
        log_memory_event(
            "ignored",
            scope="session",
            reason=decision.reason,
            importance_score=decision.importance_score,
        )

    await clear(session_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="dispatch_memory_summarization",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def dispatch_memory_summarization(self: Any, session_id: str, tenant_id: str) -> None:
    asyncio.run(_run_memory_summarization(uuid.UUID(session_id), uuid.UUID(tenant_id)))
