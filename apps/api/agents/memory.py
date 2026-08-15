"""Memory Agent (roadmap step 165, AGENTS.md's own "MEMORY AGENT"
section) -- graduates from the skeleton step 144 left it as. AGENTS.md
lists many responsibilities (short/long-term/conversation/user/
organization memory, retrieval, updates, summarization, cleanup,
confidence, expiration, quality), but step 165's own literal wording
scopes this step to exactly one of them: "decide what deserves
long-term retention -- not every conversation should become permanent
memory." The rest are each their own later roadmap step (166
retrieval, 167 summarization, 168 expiration, ...), not this one's job.

`run()` is a pure decision function -- `Message` in, `RetentionDecision`
out -- deliberately NOT the thing that writes a `models/memory.py:
Memory` row itself. Every other real agent that touches a repository
(`agents/retriever.py:RetrieverAgent`) does so through its own
dedicated methods, never through the generic `Agent.run()` contract;
`PlanningAgent.run()` similarly just returns a `Plan`, it doesn't
execute it. Actually creating the row from a real conversation is a
future caller's job (Milestone 6's conversation engine, once it
exists) -- there is no real caller today that could supply a genuine
`tenant_id`/`scope`/`session_id` to write with, so wiring persistence
in here now would be guessing at a shape nothing has asked for.

No LLM call: no agent in this codebase calls a chat/generation model
yet (`llm/openai.py`/`llm/anthropic.py`, 151-152, have no real caller),
so an "intelligent" retention judgment would be dishonest scaffolding.
Same discipline `agents/planning.py:PlanningAgent` already applied to
its own decision --  a real, deterministic heuristic, not a fake ML
judgment: very short content (`_MIN_CONTENT_LENGTH`) is almost always
noise ("ok", "thanks", "yes") and scores low; content containing an
explicit identity/preference signal phrase (the kind AGENTS.md's own
"PERSONALIZED EXPERIENCE" section names -- name, email, preferences,
"remember this") scores high; anything else substantive but signal-
free lands in between, worth a second look later (e.g. summarization,
167) rather than a confident permanent/not-permanent call today.
`importance_score` reuses step 164's own 0.0-1.0 convention directly,
so a real caller can pass this decision's score straight into
`MemoryRepository.create(...)` unchanged.
"""

from dataclasses import dataclass

from agents.base import Agent
from llm.base import Message

_MIN_CONTENT_LENGTH = 15  # chars -- shorter is almost always noise

_RETENTION_SIGNAL_PHRASES = (
    "my name is",
    "i prefer",
    "i always",
    "i never",
    "remember that",
    "remember this",
    "please remember",
    "my email is",
    "for future reference",
)

RETENTION_THRESHOLD = 0.5


@dataclass(frozen=True)
class RetentionDecision:
    should_retain: bool
    importance_score: float
    reason: str


class MemoryAgent(Agent[Message, RetentionDecision]):
    name = "memory"

    async def run(self, input: Message) -> RetentionDecision:
        stripped = input.content.strip()

        if len(stripped) < _MIN_CONTENT_LENGTH:
            score = 0.1
            reason = "too short to carry lasting information"
        elif any(phrase in stripped.lower() for phrase in _RETENTION_SIGNAL_PHRASES):
            score = 0.9
            reason = "contains an explicit identity or preference signal"
        else:
            score = 0.4
            reason = "substantive content with no explicit retention signal"

        return RetentionDecision(
            should_retain=score >= RETENTION_THRESHOLD,
            importance_score=score,
            reason=reason,
        )
