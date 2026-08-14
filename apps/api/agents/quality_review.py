"""Quality Review Agent skeleton (roadmap step 147, AGENTS.md SECTION
"QUALITY REVIEW AGENT" -- "before returning important responses,
evaluate: accuracy, completeness, relevance, consistency, citation
quality, confidence, missing information, potential hallucinations,
unsafe responses; if quality is insufficient, request improvements
before returning results").

A genuine skeleton, the same shape/reasoning `agents/memory.py`/
`agents/conversation.py`/`agents/reasoning.py` established at steps
144-146: a real class with a real `name`, no real logic -- reviewing a
generated response's accuracy/hallucinations/quality needs a real
response to review in the first place, and no chat/generation model
exists anywhere in this codebase yet (that's steps 150+).

`run()` is deliberately left unimplemented (`agents/base.py`'s own
`NotImplementedError` default), not a stub silently returning empty/
`None` -- a stub would dishonestly imply a real quality-review
capability that doesn't exist yet. Registering this agent (`agents/
registry.py:AgentRegistry`, step 139) makes it discoverable while
`health_check()` honestly reports it unhealthy until a real
implementation exists. `Agent[Any, Any]`, matching every other
not-yet-`run()`-implementing agent in this codebase.
"""

from typing import Any

from agents.base import Agent


class QualityReviewAgent(Agent[Any, Any]):
    name = "quality_review"
