"""Follow-up-question suggestion generation (roadmap step 190,
Milestone 6). AGENTS.md's own "FOLLOW-UP QUESTIONS" section describes
genuinely contentful suggestions (related documents, next logical
actions, knowledge exploration, workflow continuation, clarification
requests) -- none of that is honestly producible without real
reasoning over the actual exchange, so this calls a real LLM provider
directly, the same "first task calling a real LLM provider directly,
not through an agent" shape memory_summarization.py already
established at step 167 -- this is the second such caller, not a new
pattern.

Deliberately a SEPARATE endpoint from message-send
(`routers/conversation.py:generate_message_follow_up_questions`), not
something computed inline during `send_message`/`send_message_
streaming` -- those two endpoints have worked in every environment,
including this one with no real `OPENAI_API_KEY`, since step 143's own
"the one retrieval mechanism that works for real everywhere" design;
folding a mandatory LLM call into them would break that property for
every message, not just this one feature. Same "separate endpoint,
own accepted environment-specific gap" precedent `routers/retrieval.
py:dense_search` and `routers/conversation.py:search_conversations_
semantic` already established -- this fails closed with a plain 500
here too, not a client-facing 4xx.

Not stored on `Message` -- unlike `citations`, suggestions are a
real-time UI nicety with no archival/search value of their own
(AGENTS.md's own "avoid repetitive suggestions" reads as "let them
vary," not "make them reproducible"), so caching would be
speculative machinery this step never asked for. Reuses `repositories/
message.py:get_preceding_user_message` (188) to find the real query
half of the exchange -- the identical "find what the user actually
asked" problem regenerate already solved, not a second implementation.

`_llm_provider` is its own module-level `OpenAIProvider()` singleton,
same "each consuming module gets its own instance" pattern every other
real provider singleton in this codebase already uses (routers/
conversation.py's own `_embedding_provider`, memory_summarization.py's
own `_llm_provider`).

Basic list-marker stripping (`_strip_list_marker`) is real, deliberate
defensive parsing -- the system prompt asks for "one per line, no
numbering," but a real LLM doesn't always comply exactly (confirmed as
a real, common failure mode for this class of prompt, not a
theoretical one), and a raw "1. What ...?" line would otherwise leak
into a suggestion a client displays verbatim.
"""

import re

from llm.base import LLMProvider, Message
from llm.openai import OpenAIProvider

_llm_provider: LLMProvider = OpenAIProvider()

_FOLLOW_UP_SYSTEM_PROMPT = (
    "Based on this exchange between a user and an AI assistant, suggest "
    "up to 3 short, natural follow-up questions the user might want to ask "
    "next. Write one question per line, with no numbering, bullets, or "
    "extra commentary."
)

_LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s*")


def _strip_list_marker(line: str) -> str:
    return _LIST_MARKER.sub("", line).strip()


async def generate_follow_up_questions(user_query: str, assistant_response: str) -> list[str]:
    messages = [
        Message(role="system", content=_FOLLOW_UP_SYSTEM_PROMPT),
        Message(role="user", content=user_query),
        Message(role="assistant", content=assistant_response),
    ]
    response = await _llm_provider.complete(messages)
    return [
        stripped for line in response.content.splitlines() if (stripped := _strip_list_marker(line))
    ]
