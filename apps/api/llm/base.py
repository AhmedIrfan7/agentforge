"""LLMProvider (roadmap step 150) -- a structural Protocol, same
interface-first precedent `embeddings/base.py:EmbeddingProvider` (106)
and `vectorstore/base.py:VectorStore` (118) already established.

Message-based (a list of role/content turns), not a single prompt
string -- every real LLM provider this roadmap will actually implement
(151 OpenAI, 152 Anthropic) is a chat/messages API, not a legacy
single-prompt completion API, and this codebase's own Conversation
Agent/Conversation Engine (Milestone 6) already commit to multi-turn
conversation being the real shape a caller needs. `Role` includes
"system" even though Anthropic's real Messages API takes system
instructions as a separate top-level parameter, not a role inside the
messages list -- that's a real, known provider-specific quirk step
152's own adapter will translate (extracting any `role="system"`
messages and passing them through Anthropic's own `system` parameter),
the same "same interface, each provider translates its own API's real
shape" pattern `auth/oauth.py`'s provider adapters already use; the
shared interface itself should stay the portable, common shape, not
bend to one provider's own quirk.

`LLMResponse` carries real, checkable usage data (`prompt_tokens`/
`completion_tokens`) -- step 153 ("per-agent execution tracing:
latency/tokens/status") is already known to need real token counts,
and only a provider's own API response can honestly report them.
Latency is deliberately NOT part of this interface -- any caller can
already measure it externally via wall-clock time around the call
(the same "own real output shape, don't duplicate what a caller can
already measure" reasoning kept `context_builder.py:ContextChunk` from
carrying a ranking `score` it didn't need). No streaming method --
nothing in this roadmap's own sequencing (150-161) ever asks for
token-by-token streaming; adding one now would be speculative, the
same "add the field/method when the step that needs it lands"
discipline this project has followed since step 106.

`LLMProviderError` mirrors `embeddings/openai.py:EmbeddingProviderError`
-- a single type for any real provider failure (auth, rate limit,
network, malformed response), so a future dispatcher can catch one
thing regardless of which provider is behind `LLMProvider`.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int


class LLMProviderError(Exception):
    pass


class LLMProvider(Protocol):
    name: str

    async def complete(self, messages: list[Message]) -> LLMResponse: ...
