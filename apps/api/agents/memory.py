"""Memory Agent skeleton (roadmap step 144, AGENTS.md SECTION "MEMORY
AGENT" -- responsible for short-term/long-term/conversation/user/
organization memory, memory retrieval/updates/summarization/cleanup,
memory confidence/expiration/quality; "determine what information
deserves long-term retention -- not every conversation should become
permanent memory").

A genuine skeleton, the same shape `agents/document_analysis.py`/
`agents/chunking_recommendation.py` originally had (steps 095/097): a
real class with a real `name`, no real logic behind it yet -- no
`Memory` model or migration exists anywhere in this codebase (that's
Milestone 5, steps 162-175), so there is nothing real for `run()` to
call into.

`run()` is deliberately left unimplemented (`agents/base.py`'s own
`NotImplementedError` default), not a stub silently returning empty/
`None` -- a stub would dishonestly imply "memory was checked, nothing
found" when the true state is "memory doesn't exist as a concept in
this codebase yet." This is exactly the real scenario `agents/
registry.py:AgentRegistry.health_check()` (step 139) was designed to
distinguish: a future caller can register this agent (making it real
and discoverable) while `health_check()` honestly reports it unhealthy
until a real Milestone 5 implementation overrides `run()`.
`Agent[Any, Any]` -- same reasoning `DocumentAnalysisAgent`/
`ChunkingRecommendationAgent`/`RetrieverAgent` already established for
not participating in the typed `run()` contract.
"""

from typing import Any

from agents.base import Agent


class MemoryAgent(Agent[Any, Any]):
    name = "memory"
