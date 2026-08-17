# Extension points

Where AgentForge is built to grow a second real implementation without a
rewrite, and where it deliberately isn't. Every interface below is a
`typing.Protocol` in the codebase today, not a plan — this documents what
already exists, not a roadmap.

## Provider interfaces designed for multiple real implementations

These have a `PROVIDERS: dict[str, ...]` registry because the codebase
already has two or more real, independent implementations behind the
same interface.

### LLM providers — `apps/api/llm/`

`llm/base.py:LLMProvider` — one async method, `complete(messages) ->
LLMResponse`, message-based (role/content turns), returning real
`prompt_tokens`/`completion_tokens` usage. `llm/__init__.py:PROVIDERS`
currently holds `openai` (`llm/openai.py:OpenAIProvider`) and
`anthropic` (`llm/anthropic.py:AnthropicProvider`). Both raise a single
`LLMProviderError` on any real failure (auth, rate limit, network,
malformed response), so a caller catches one thing regardless of which
provider is behind it.

To add a provider: implement `LLMProvider`, translate the target API's
own request/response shape to `Message`/`LLMResponse` inside the
adapter (see `AnthropicProvider` for a real example — Anthropic's
Messages API takes `system` as a separate top-level parameter, not a
message role, and the adapter handles that translation internally so
the shared interface stays provider-agnostic), register it in
`PROVIDERS`, and add tests following `tests/test_openai_llm_provider.py`
/ `tests/test_anthropic_llm_provider.py` plus
`tests/test_llm_providers_registry.py` for the registry-level contract.

### OAuth providers — `apps/api/auth/oauth.py`

`OAuthProvider` Protocol, `PROVIDERS` registry. `GoogleOAuthProvider` is
the one real implementation today; the interface and registry exist
because this codebase's own history shows the concrete-then-Protocol
progression (`GoogleOAuthProvider` was interface-free until a second
real provider justified generalizing it) — adding a second OAuth
provider (GitHub, Microsoft, etc.) follows the same shape: implement the
Protocol, register it, add tests alongside the existing Google ones.

## Provider interfaces with one real implementation today, built to add a second

These are already `Protocol`-based (not concrete classes wired inline),
but don't have a `PROVIDERS` registry yet — this codebase's own
"don't build the registry before there's a second real entry to put in
it" rule, applied consistently across every provider package.

### Embedding providers — `apps/api/embeddings/`

`embeddings/base.py:EmbeddingProvider` — `embed(texts) ->
list[list[float]]`, plus a `dimensions` attribute a caller can check
without making a call. `embeddings/openai.py:OpenAIEmbeddingProvider` is
the only implementation. A second provider is a real, supported case —
implement the Protocol, then add a `PROVIDERS` dict to
`embeddings/__init__.py` the way `llm/__init__.py` did once it had two
providers. See `tests/test_openai_embedding_provider.py` and
`tests/test_embedding_provider.py` for the existing test shape.

### Speech-to-text / text-to-speech — `apps/api/voice/`

`voice/base.py:SpeechToTextProvider` (`transcribe`) and
`TextToSpeechProvider` (`synthesize`) are two separate Protocols, not
one — a provider can implement either without the other.
`voice/whisper.py:WhisperSTTProvider` and
`voice/openai_tts.py:OpenAITTSProvider` are the current implementations.
Both raise `SpeechProviderError` on any real failure. See
`tests/test_voice_provider.py`.

## Interfaces that exist for structure, not for swapping

These are `Protocol`s too, but the codebase has explicitly decided they
are not expected to ever grow a second real implementation — documented
here so a contributor doesn't spend effort building registry machinery
these packages deliberately don't have.

### Vector store — `apps/api/vectorstore/base.py:VectorStore`

`ADR-0001` (`docs/adr/0001-technology-stack.md`) locks in pgvector as
this project's one and only vector store. `vectorstore/pgvector.py:
PgVectorStore` is the sole implementation, and there's no second one
planned anywhere in `docs/ROADMAP.md`. The interface exists for
testability (mocking `VectorStore` in tests that don't need a real
Postgres) more than for provider substitution.

### Reranker — `apps/api/rerankers/base.py:RerankerProvider`

Same reasoning — `rerankers/lexical.py:LexicalReranker` is expected to
stay the only implementation; no second reranker appears anywhere in
the roadmap.

## Agents — `apps/api/agents/`

`agents/base.py:Agent[InputT, OutputT]` is the shared contract a
LangGraph orchestrator node needs to invoke any agent generically:
`config: dict[str, Any]` plus an async `run(input) -> output`. It's
generic per-agent, not a fixed input/output shape, since each domain
(memory, conversation, reasoning, quality review, safety, citation) has
its own real shape. `run()` is deliberately not an abstract method —
some existing agents (`DocumentAnalysisAgent`,
`ChunkingRecommendationAgent`, `agents/retriever.py:RetrieverAgent`)
predate this contract and keep their own domain-specific methods as
their real API, used directly by their real callers outside the
orchestrator graph.

`agents/registry.py:AgentRegistry` (module-level singleton
`agent_registry`) is where a new agent gets discovered at runtime:
`register(agent)`, `get(name)`, `discover()` (list every registered
name), and `health_check()` — which reports whether each agent's
`run()` was actually overridden, not a network liveness probe, since
registration and readiness are deliberately separate concerns.

To add a new agent for the orchestrator: subclass `Agent[InputT,
OutputT]`, implement `run()`, register an instance with
`agent_registry.register(...)`. To wrap an existing domain-specific
agent (one with its own real methods and callers, like
`RetrieverAgent`) for graph use without rewriting it, add a thin adapter
that satisfies `Agent`'s `run()` contract by delegating to the agent's
real method — the same pattern step 143 used to wire `RetrieverAgent`
into the orchestrator graph.

## Widget — `apps/widget/`

Framework-free vanilla TypeScript by design (`docs/adr/0001-technology-
stack.md`), embedded via a single `<script>` tag. There's no plugin API
today — extending widget behavior means editing `apps/widget/src/`
directly. Not a gap tracked anywhere in `docs/ROADMAP.md`'s remaining
steps.
