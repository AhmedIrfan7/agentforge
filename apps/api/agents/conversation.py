"""Conversation Agent skeleton (roadmap step 145, AGENTS.md SECTION
"CONVERSATION AGENT" -- responsible for managing conversations,
maintaining conversational flow, understanding follow-up questions,
handling interruptions, conversation summarization, conversation
continuity, response formatting, conversation state; "focuses on user
interaction quality").

A genuine skeleton, the same shape/reasoning `agents/memory.py`
established at step 144: a real class with a real `name`, no real
logic -- no conversation/session model or migration exists anywhere in
this codebase yet (that's Milestone 6, steps 176-200), so there is
nothing real for `run()` to call into.

`run()` is deliberately left unimplemented (`agents/base.py`'s own
`NotImplementedError` default), not a stub silently returning empty/
`None` -- a stub would dishonestly imply a real conversation-handling
capability that doesn't exist yet. Registering this agent (`agents/
registry.py:AgentRegistry`, step 139) makes it discoverable while
`health_check()` honestly reports it unhealthy until Milestone 6 gives
it a real implementation. `Agent[Any, Any]`, matching every other
not-yet-`run()`-implementing agent in this codebase.
"""

from typing import Any

from agents.base import Agent


class ConversationAgent(Agent[Any, Any]):
    name = "conversation"
