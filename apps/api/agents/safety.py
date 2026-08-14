"""Safety Agent skeleton (roadmap step 148, AGENTS.md SECTION "SAFETY
AGENT" -- responsible for prompt injection detection, malicious
instructions, unsafe tool usage, data leakage prevention, cross-tenant
protection).

A genuine skeleton, the same shape/reasoning `agents/memory.py`/
`agents/conversation.py`/`agents/reasoning.py`/`agents/quality_review.
py` established at steps 144-147: a real class with a real `name`, no
real logic -- detecting prompt injection/malicious instructions in a
user query or unsafe tool usage in an agent's own output needs a real
chat/generation and tool-execution pipeline to guard, and neither
exists anywhere in this codebase yet (that's steps 150+ for a real LLM
provider; no agent here calls tools at all yet). Cross-tenant
protection specifically is already real, tested infrastructure
elsewhere in this codebase (Postgres RLS + `repositories/base.py:
TenantScopedRepository`, `tests/test_tenant_isolation.py`/`tests/
test_retrieval_tenant_isolation.py`) -- this agent doesn't duplicate
that; a future real implementation would compose with it, not replace
it.

`run()` is deliberately left unimplemented (`agents/base.py`'s own
`NotImplementedError` default), not a stub silently returning empty/
`None`/"safe" -- a stub that always reports "safe" would be actively
dangerous, not just dishonest: a caller checking `run()`'s result
before proceeding would be worse off trusting a fake, no-op verdict
than seeing a genuine `NotImplementedError`. Registering this agent
(`agents/registry.py:AgentRegistry`, step 139) makes it discoverable
while `health_check()` honestly reports it unhealthy until a real
implementation exists. `Agent[Any, Any]`, matching every other
not-yet-`run()`-implementing agent in this codebase.
"""

from typing import Any

from agents.base import Agent


class SafetyAgent(Agent[Any, Any]):
    name = "safety"
