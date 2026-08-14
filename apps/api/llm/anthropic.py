"""Anthropic LLM provider (roadmap step 152) -- the second real
`llm/base.py:LLMProvider`, following `llm/openai.py`'s own established
shape (direct httpx, no vendor SDK) with the real shape differences
Anthropic's Messages API has -- verified live against Anthropic's own
current docs (platform.claude.com/docs/en/api/messages, fetched
2026-08, docs.claude.com redirects there) before writing this, matching
this project's "verify any new library/API surface live" discipline
already used for LangGraph (137) and OpenAI (151).

Three real, confirmed-live differences from `llm/openai.py`:

1. `system` is a top-level request parameter, not a message with
   role="system" -- `llm/base.py`'s own step-150 docstring already
   flagged this exact translation as this step's job. `_split_system`
   pulls any role="system" messages out of the input list (joined, in
   case more than one is ever passed) and sends the remainder as the
   `messages` array.

2. `max_tokens` is a REQUIRED request field here (unlike OpenAI's Chat
   Completions, which defaults it server-side) -- picked a fixed,
   generous default (`_MAX_TOKENS`) since no real caller commits this
   codebase to a specific length budget yet, the same "no real caller
   yet" reasoning `llm/openai.py`'s own model choice used.

3. Auth is an `x-api-key` header plus a required `anthropic-version`
   header, not a Bearer `Authorization` header -- confirmed live, a
   genuine difference from OpenAI's convention rather than something
   to copy from `llm/openai.py`.

Response shape also differs: `content` is an array of typed blocks
(text/tool_use/thinking/...) rather than OpenAI's single
`message.content` string. This provider only ever sends plain text
messages (no tools, no extended thinking), so it takes the first block
of type "text" and raises `LLMProviderError` if none exists, rather
than assuming `content[0]` is always text. Token usage fields are named
differently too: `usage.input_tokens`/`usage.output_tokens` map to
`LLMResponse.prompt_tokens`/`completion_tokens`.

Model: `claude-haiku-4-5`, Anthropic's own current fastest/cheapest
tier (confirmed live) -- same "cheapest current model, no real caller
commits to a quality tier yet" reasoning `llm/openai.py` and
`embeddings/openai.py` already used for their own model choices.

Live-probe finding (real api.anthropic.com, this environment's empty
`anthropic_api_key`): a clean, server-returned 401 -- NOT the client-
side `httpx.LocalProtocolError` `llm/openai.py`'s own step-151 probe
hit. Anthropic's `x-api-key` header takes the raw key with no prefix,
so an empty key produces a syntactically valid (if empty) header value
that httpx's own client-side validation has no reason to reject, unlike
OpenAI's `f"Bearer {key}"`, where an empty key leaves a trailing space
that httpx does reject before the request ever leaves the machine. Same
observable behavior either way (a clean `LLMProviderError`), but a
genuinely different failure mode underneath -- worth noting since the
two providers' auth header conventions differ enough that the same
"empty key" input fails at different layers.
"""

from typing import Any

import httpx

from config import settings
from llm.base import LLMProviderError, LLMResponse, Message


class AnthropicProvider:
    name = "anthropic"

    _MESSAGES_URL = "https://api.anthropic.com/v1/messages"
    _MODEL = "claude-haiku-4-5"
    _ANTHROPIC_VERSION = "2023-06-01"
    _MAX_TOKENS = 4096

    async def complete(self, messages: list[Message]) -> LLMResponse:
        system_text, remaining = _split_system(messages)
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                body: dict[str, Any] = {
                    "model": self._MODEL,
                    "max_tokens": self._MAX_TOKENS,
                    "messages": [{"role": m.role, "content": m.content} for m in remaining],
                }
                if system_text:
                    body["system"] = system_text
                response = await client.post(
                    self._MESSAGES_URL,
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": self._ANTHROPIC_VERSION,
                    },
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
                text_block = next(
                    (block["text"] for block in payload["content"] if block["type"] == "text"),
                    None,
                )
                if text_block is None:
                    raise LLMProviderError("Anthropic response contained no text content block.")
                usage = payload["usage"]
                return LLMResponse(
                    content=text_block,
                    prompt_tokens=usage["input_tokens"],
                    completion_tokens=usage["output_tokens"],
                )
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                raise LLMProviderError("Anthropic message request failed.") from exc


def _split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    system_parts = [m.content for m in messages if m.role == "system"]
    remaining = [m for m in messages if m.role != "system"]
    return "\n\n".join(system_parts), remaining
