"""OpenAI LLM provider (roadmap step 151) -- the first real
`llm/base.py:LLMProvider`. Speaks OpenAI's Chat Completions REST API
directly over httpx, same reasoning `embeddings/openai.py:
OpenAIEmbeddingProvider` already established for this project's other
OpenAI adapter: a direct, authenticated server-to-server call, so a
vendor SDK buys nothing a raw HTTP client doesn't already give for one
endpoint.

Chat Completions (`/v1/chat/completions`), not the newer Responses API
-- checked live (OpenAI's own current API docs, fetched 2026-08)
before choosing: Chat Completions is explicitly "supported
indefinitely" even though Responses is now OpenAI's own recommended
surface for brand-new integrations. Chat Completions' exact shape
(`messages` in, `choices[0].message.content`/`usage.prompt_tokens`/
`usage.completion_tokens` out) is exactly what `llm/base.py:Message`/
`LLMResponse` were already designed to mirror, and it's one of the
most stable, longest-unchanged request/response shapes in the
industry -- the safer, higher-confidence choice over building against
a newer API surface this project has no other real experience with
yet. `Message.role` needs no translation for this provider (unlike a
future Anthropic adapter, per `llm/base.py`'s own docstring) --
Chat Completions natively accepts `"system"` as a normal message role.

`gpt-5.6-luna` chosen as the default model: OpenAI's own current
lightest/cheapest chat-completions tier (checked live against OpenAI's
own docs, 2026-08 -- "recommended for cost-sensitive, high-volume
deployments"), the same "cheapest current model, not a speculative
mid-tier compromise" reasoning `embeddings/openai.py` already used
choosing `text-embedding-3-small` -- no real caller commits this
codebase to a specific quality/cost tradeoff yet (every agent that
would call this, steps 144-148, is still an honestly-unimplemented
skeleton), so the honest, cost-conscious default is the right one
until a real need says otherwise.
"""

import httpx

from config import settings
from llm.base import LLMProviderError, LLMResponse, Message


class OpenAIProvider:
    name = "openai"

    _COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
    _MODEL = "gpt-5.6-luna"

    async def complete(self, messages: list[Message]) -> LLMResponse:
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    self._COMPLETIONS_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={
                        "model": self._MODEL,
                        "messages": [{"role": m.role, "content": m.content} for m in messages],
                    },
                )
                response.raise_for_status()
                payload = response.json()
                choice = payload["choices"][0]
                usage = payload["usage"]
                return LLMResponse(
                    content=choice["message"]["content"],
                    prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"],
                )
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                raise LLMProviderError("OpenAI chat completion request failed.") from exc
