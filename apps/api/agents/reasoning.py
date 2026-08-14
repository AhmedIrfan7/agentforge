"""Reasoning Agent skeleton (roadmap step 146, AGENTS.md SECTION
"REASONING AGENT" -- responsible for breaking down complex questions,
multi-step reasoning, planning reasoning steps, evaluating
intermediate conclusions, supporting the orchestrator with complex
problem solving; "avoid unnecessary reasoning for simple questions").

A genuine skeleton, the same shape/reasoning `agents/memory.py`/
`agents/conversation.py` established at steps 144/145: a real class
with a real `name`, no real logic -- multi-step reasoning over complex
questions needs a real chat/generation model, and none exists anywhere
in this codebase yet (that's steps 150+, LLM-provider abstraction and
OpenAI/Anthropic implementations).

`run()` is deliberately left unimplemented (`agents/base.py`'s own
`NotImplementedError` default), not a stub silently returning empty/
`None` -- a stub would dishonestly imply a real reasoning capability
that doesn't exist yet. Registering this agent (`agents/registry.py:
AgentRegistry`, step 139) makes it discoverable while `health_check()`
honestly reports it unhealthy until a real LLM-backed implementation
exists. `Agent[Any, Any]`, matching every other not-yet-`run()`-
implementing agent in this codebase.
"""

from typing import Any

from agents.base import Agent


class ReasoningAgent(Agent[Any, Any]):
    name = "reasoning"
