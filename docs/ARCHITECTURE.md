# AgentForge Architecture

This document describes the system **as implemented**, not as aspired to — it grows one section at a time as each subsystem lands, per the checkpoints built into `docs/ROADMAP.md`. For the full product/engineering vision this architecture serves, see [`AGENTS.md`](../AGENTS.md). For why specific technologies were chosen, see [`docs/adr/`](adr/).

## Status

Milestone 8 (Voice Platform) complete; Milestone 9 (Admin Dashboard & Analytics) next. Sections below are filled in as the corresponding roadmap milestone completes — an empty section means that subsystem doesn't exist yet, not that it was forgotten. (Authentication & authorization, Milestone 2, is also built — its section is still a placeholder below; that's a documentation gap to close, not a sign the subsystem is missing.)

## Repository layout

```
apps/
  api/      FastAPI backend — REST API, multi-agent orchestrator, RAG pipeline, background workers
  web/      Next.js admin dashboard
  widget/   Embeddable chat/voice widget (vanilla TS)
packages/
  shared/   Cross-app TypeScript contracts
infra/      Docker, deployment, infrastructure-as-code
docs/       This file, ADRs, roadmap
```

## Local development

- `apps/api`: Python + FastAPI, dependencies managed with `uv`. Lint/format with `ruff`, type-check with `mypy` (strict), test with `pytest`.
- `apps/web`: Next.js (App Router) + TypeScript, dependencies managed with `pnpm` in a workspace. Lint with `eslint`, format with `prettier`.
- `packages/shared`: consumed as source directly, no build step.
- Local services (Postgres+pgvector, Redis, MinIO) run via `docker-compose.yml`.
- Database schema is managed with Alembic (`apps/api/migrations/`, async template). `make api-migrate` applies migrations, `make api-seed` creates a demo org/workspace/user (idempotent — safe to re-run).
- See the root `Makefile` for common commands.

## Multi-tenancy

Full design rationale and the alternatives considered live in [`docs/adr/0003-multi-tenancy-isolation-strategy.md`](adr/0003-multi-tenancy-isolation-strategy.md). This section is the as-built summary.

### Isolation model

Single shared Postgres database. Every tenant-scoped table carries a `tenant_id` column and a Postgres Row-Level Security policy, enforced at **two independent layers** (defense-in-depth, per `AGENTS.md` §9):

1. **Database layer (Postgres RLS).** Every tenant-scoped table has `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`, plus a `tenant_isolation` policy comparing `tenant_id` against the `app.current_tenant_id` session variable. No `app.current_tenant_id` set means no rows visible — fails closed by default. Reusable helpers: `apps/api/migrations/rls.py:enable_rls()` / `disable_rls()`, called from each tenant-scoped table's own creation migration (not bolted on afterward).
2. **Application layer (repository).** `apps/api/repositories/base.py:TenantScopedRepository` filters every query by `tenant_id` explicitly and ignores any caller-supplied `tenant_id` on create. This exists so a bug shows up as "wrong data in a test" long before anyone has to rely on RLS catching it in production.

**Critical operational detail:** Postgres superusers bypass RLS unconditionally, `FORCE` notwithstanding. The `docker-compose.yml` bootstrap role (`POSTGRES_USER=agentforge`) is always a superuser — that's fixed behavior of the official Postgres image. The running application therefore connects as a second, deliberately unprivileged role (`agentforge_app`, see `infra/postgres/init/01-app-role.sql`) that has no `BYPASSRLS`, isn't a superuser, and isn't a table owner — RLS actually applies to it. Migrations still run as the bootstrap superuser (DDL needs elevated rights). Two separate connection strings exist in `apps/api/config.py`: `database_url` (app runtime) and `database_migrations_url` (Alembic only). This split exists because an earlier verification pass — testing via the superuser role — falsely appeared to show RLS not working at all.

### Tenant hierarchy (as built so far)

```
Organization (tenant root — no tenant_id, IS the tenant boundary)
  └─ Workspace (tenant_id = organization_id)
       └─ Membership (tenant_id = organization_id; links User ↔ Organization ↔ optional Workspace ↔ Role)
User (global identity — one row per person, not tenant-scoped; scoped via Membership)
Role / Permission / RolePermission (global catalog, not tenant-scoped — shared built-in roles)
AuditLog (tenant_id, but intentionally no FK to Organization — an audit trail should outlive the org it's about)
```

`Membership.workspace_id` is nullable to support both org-level and workspace-specific membership — enforced with two partial unique indexes rather than a plain `UniqueConstraint`, since Postgres treats `NULL != NULL` and a naive constraint would silently allow duplicate org-level memberships.

### Setting tenant context

`apps/api/db.py:set_tenant_context(session, tenant_id)` issues `SET LOCAL app.current_tenant_id = '<uuid>'` — inlined into the SQL text (Postgres's `SET`/`SET LOCAL` don't accept bind parameters), safe here specifically because `tenant_id` is a `uuid.UUID` Python object, not a raw string. `SET LOCAL` only lasts for the current transaction; each new transaction on a session needs it set again.

FastAPI routes get this automatically via `apps/api/dependencies/tenant.py:get_tenant_db` — a per-request dependency that resolves a trusted `tenant_id` and calls `set_tenant_context()` before yielding the session, then auto-commits on success / rolls back on any exception. **How `tenant_id` gets resolved is still a placeholder** (`get_current_tenant_id()` raises `NotImplementedError`) until Milestone 2's authentication exists — deliberately, not a shortcut that trusts a client-supplied header (`AGENTS.md` §9 is explicit that tenant context must never come from client input). Routes wired against `get_tenant_db` today (e.g. `routers/workspace.py`) are correctly built but non-functional until then; they need zero route-code changes once real auth lands.

### Testing tenant isolation

`apps/api/tests/test_tenant_isolation.py` proves cross-tenant reads are blocked, cross-tenant writes are rejected (`WITH CHECK` violation), and the system fails closed with no tenant context set — against a real Postgres connection using the actual least-privilege `agentforge_app` role, not mocked and not tested through the superuser connection (which would pass regardless of whether RLS worked). `tests/test_repository_base.py` and `tests/test_tenant_dependency.py` prove the same property holds through the repository layer and the FastAPI dependency chain respectively.

## Authentication & authorization

_To be filled in as Milestone 2 lands._

## Knowledge pipeline & RAG

Two halves, built in sequence: **ingestion** (steps 82–117) turns an uploaded file into searchable, embedded chunks; **retrieval** (steps 118–135) turns a free-text query into a ranked, cited, token-budgeted context an LLM could consume. No chat/generation model is chosen yet (Milestone 4+) — every retrieval-facing capability here was built and proven as its own real, tested unit, not against an imagined downstream consumer.

### Ingestion

`POST .../knowledge-bases/{id}/documents` accepts a multipart upload, validates it (file-type allow-list, size limit, a real ClamAV scan — not stubbed), and stores the raw file in MinIO/S3-compatible storage (`storage.py`, aioboto3). A Celery + Redis background pipeline then runs, with per-stage status visible through a pipeline-status endpoint and real retry/backoff (not just a `max_retries` number nobody wired up) on every stage:

1. **Extraction** (`extraction_pdf.py`/`extraction_docx.py`/etc., dispatched per file type) — every format normalizes to the same markdown shape (`# `/`## ` headings, `| … |` pipe tables), which is what lets every downstream stage (chunking, section-aware citations) work uniformly regardless of source format.
2. **Metadata extraction** — title, author, dates, language.
3. **Document Analysis Agent** (`agents/document_analysis.py`) — classifies document type via keyword-phrase scoring, honestly heuristic, not an ML model.
4. **Quality checks** — empty pages, broken formatting, duplicate-content hash.
5. **Chunking Recommendation Agent** (`agents/chunking_recommendation.py`) — scores five real chunking strategies (fixed-size, sentence/paragraph, markdown-heading, table-aware, recursive-hybrid) against the document's actual structure and explains its choice; overridable per-document via a dedicated endpoint.
6. **Embedding generation** — `embeddings/base.py:EmbeddingProvider` (structural Protocol, interface-first) with `embeddings/openai.py:OpenAIEmbeddingProvider` (`text-embedding-3-small`, 1536-d) the one real implementation.
7. **Vector storage** — `Chunk.embedding` (pgvector `Vector(1536)`, ivfflat index) plus `Chunk.search_vector` (a DB-computed `tsvector`, GIN-indexed) for full-text search — both populated from the same chunk row, never able to drift out of sync.

Document lifecycle beyond first upload: re-indexing (re-runs extraction→embedding, old chunks kept until the new run succeeds), versioning (replace preserves history), tenant-scoped deletion (cascades chunks/embeddings, deletes the storage object first), and duplicate-document detection within a knowledge base (by content hash).

**Real, tracked environment gap:** no `OPENAI_API_KEY` exists in this project's dev/CI environment. Every embedding-dependent code path is real, not stubbed — it's tested against a fake `EmbeddingProvider` and separately live-verified to fail closed with a clean 500 (not a leaked stack trace) when the real key is absent, rather than being silently skipped.

### Retrieval

`vectorstore/base.py:VectorStore` (structural Protocol, interface-first) with `vectorstore/pgvector.py:PgVectorStore` the one real implementation — deliberately no provider registry, since nothing in this roadmap ever adds a second vector store. Three real retrieval mechanisms exist as genuinely different techniques, not modes of one abstraction:

- **Dense** (cosine similarity via pgvector).
- **Keyword** (`ChunkRepository.search_by_keyword` — Postgres full-text, `plainto_tsquery`/`ts_rank`; the one mechanism that works with no external API key).
- **Hybrid** — runs both and fuses their ranked lists with Reciprocal Rank Fusion (`retrieval_fusion.py`), the industry-standard technique for combining differently-scaled rankings.

All three support metadata filtering (`document_id`/`document_type`, the two real, populated fields — not a speculative generic filter DSL) and are wrapped behind one agent-shaped interface, `agents/retriever.py:RetrieverAgent`, matching `AGENTS.md`'s Agent Registry design. Layered on top, each an independent, explicitly opt-in stage (never silently folded into the base search calls):

- **Reranking** (`rerankers/lexical.py:LexicalReranker`) — real term-overlap scoring, not an ML cross-encoder or LLM call (none exists yet in this codebase); a genuinely different signal from both cosine similarity and `ts_rank`.
- **Multi-query expansion** (`multi_query.py`) — splits a compound query ("refund policy and shipping times") into its own clauses, retrieves each separately, and fuses via the same RRF — a deterministic heuristic, not an LLM paraphraser.
- **Parent-child retrieval** (`ChunkRepository.get_expanded_context`) — reconstructs a matched chunk's wider context from its own real neighbors (`Chunk.index`/`document_id`), not a separately stored parent-chunk row; no schema change, since nothing in this roadmap needs a genuine parent-chunk relationship.

`context_builder.py` then dedupes (by normalized text), groups chunks from the same document adjacent to each other, and fits the result to a real token budget (`tiktoken`, `cl100k_base`) — and `citations.py` attaches document/section references to what survives. Section references are parsed live from a chunk's own leading markdown heading; **page references are deliberately not supported** — every extractor joins a document's pages into one continuous string with no page boundary retained anywhere to honestly cite.

`POST .../knowledge-bases/{id}/context` is the one endpoint that composes all of the above into a real HTTP response: strategy choice (dense/keyword/hybrid), optional multi-query expansion, optional reranking, context-building, and citations — cached in Redis, keyed by a hash of tenant/knowledge-base/every request field (`routers/retrieval.py`), with a flat 5-minute TTL and **no reindex-aware invalidation** (a stated limitation, not silently worked around).

`eval/` is this pipeline's own quality-measurement layer, per `AGENTS.md`'s "do not assume retrieval quality is good, measure it": `eval/metrics.py` (precision@k/recall@k), `eval/fixtures.py` (a small, real, labeled benchmark corpus), `eval/harness.py` (seeds the corpus into real Postgres and scores a caller-supplied search function against it), and `eval/regression.py` — a real script (`python -m eval.regression`, also wrapped by a pytest test) that fails if keyword-search precision/recall on the benchmark corpus ever drops below 1.0.

Tenant isolation for retrieval specifically is covered by `tests/test_retrieval_tenant_isolation.py` — proving both raw Postgres RLS (no app-layer filter at all) and the real retrieval methods reject a genuinely valid, real `knowledge_base_id`/`chunk_id` belonging to a different tenant, not just a random never-real UUID.

**Honest, tracked gaps, not silently worked around:**
- No `OPENAI_API_KEY` in this environment — dense, hybrid, and multi-query-over-dense all fail closed with a clean 500; keyword search works for real everywhere.
- No page-number citations (extraction never retains page boundaries).
- Parent-child retrieval reconstructs a window from adjacent chunks, not a document's true stored parent-section structure.
- The Redis cache has no invalidation hook into document re-index/delete — only a 5-minute TTL.
- Reranking and multi-query expansion are real heuristics, not ML/LLM-based — no chat/generation model exists yet to build either against.

## Multi-agent system

Built in three layers, each proven independently before the next depended on it: a **LangGraph-based orchestrator** that runs a real request through a real graph, an **agent population** ranging from genuinely implemented to honestly-unimplemented skeletons, and **cross-cutting execution infrastructure** (tracing, parallelism, failure handling) that wraps every agent call uniformly.

### Agents

`agents/base.py:Agent[InputT, OutputT]` (PEP 695 generics, this codebase's enforced style over `typing.Generic`) is the shared shape: a `name` for logging/registry lookup, a generic `run(input) -> output`, deliberately **not** an `abstractmethod` — several agents (`RetrieverAgent`, `PlanningAgent`) have real, useful methods that aren't shaped like a single `run()` call and never override it. `agents/registry.py:AgentRegistry` is a real, tested, name-keyed lookup (`register`/`get`/`discover`/`health_check`) that starts empty by design — nothing constructs-and-registers agents at app startup yet, since no router depends on registry lookup today; `health_check()`'s real signal is `type(agent).run is not Agent.run`, distinguishing an agent that overrides `run()` from one that's still a skeleton.

Two genuinely different kinds of agent exist side by side, both honest about which they are:

- **Real, implemented:** `RetrieverAgent` (dense/keyword/hybrid search, reranking, multi-query, parent-child expansion — wraps Milestone 3's retrieval mechanisms behind the Agent interface), `PlanningAgent` (a real, minimal `document_search` → `["retriever"]` heuristic — not an LLM planner, since no chat model exists to plan with yet), `CitationAgent` (wraps `citations.py`'s existing real logic), `MemoryAgent` (Milestone 5, step 165 — a real, deterministic retention-decision heuristic: `run(Message) -> RetentionDecision`, scoring on content length and explicit identity/preference signal phrases, not an LLM judgment; a pure decision function with no repository dependency — persisting the decision as a real `Memory` row is a future caller's job, once Milestone 6's conversation engine exists to call it from), `DocumentAnalysisAgent`/`ChunkingRecommendationAgent` (Milestone 3's ingestion-time agents).
- **Honest skeletons:** `ConversationAgent`, `ReasoningAgent`, `QualityReviewAgent`, `SafetyAgent` — real classes with a real `name`, deliberately left `NotImplementedError` rather than stubbed to return empty/fake-safe output. Each needs infrastructure that doesn't exist yet (a conversation/session model, a real chat/generation model) or, for `SafetyAgent` specifically, would be actively dangerous to fake (a confident-looking but fake "safe" verdict is worse than an honest failure).

### Orchestrator

`orchestrator.py:Orchestrator` builds its own real, compiled LangGraph `StateGraph` in `__init__` — a genuine three-node graph (`intent_analysis → planning → execute`), not the throwaway passthrough scaffold `agent_graph.py` used to first prove LangGraph works in this codebase. `OrchestratorState` is a `TypedDict` that grew one justified field per step (`query`/`response` → `+intent` → `+agent_names` → `+tenant_id`/`+knowledge_base_id`). Intent classification is deliberately two-way (`document_search` vs. `empty`) rather than AGENTS.md's full ten-category vision — only document search has a real subsystem behind it today; building a ten-way classifier with nine dead branches would be dishonest scaffolding. `_RetrieverGraphAgent` is a thin, request-scoped adapter constructed fresh per graph node (never registered into `AgentRegistry`, whose stateless design doesn't fit a `tenant_id`/`knowledge_base_id`-bound object) — the response for a real hit is the retrieved chunks' own raw text, since no chat/generation model exists yet to synthesize an answer.

### LLM providers

`llm/base.py:LLMProvider` (structural Protocol, message-based — `list[Message]`, each a `role`/`content` turn, not a single prompt string) with two real implementations: `llm/openai.py:OpenAIProvider` (Chat Completions, not the newer Responses API — the more stable, longest-unchanged shape) and `llm/anthropic.py:AnthropicProvider` (Messages API, with two real shape differences from OpenAI it translates itself: `system` as a top-level parameter rather than a message role, and a required `max_tokens`). `llm.PROVIDERS` is a name-keyed registry of both real instances, landing at the same point `embeddings`/`auth.oauth`'s own registries did — once a genuine second implementation existed to put in it. No agent calls an LLM yet; both providers are real, tested (including live-probed failure modes against the actual APIs), and waiting for `ReasoningAgent`/`ConversationAgent` to need one.

### Execution infrastructure

Three small, composable modules wrap every real agent call:

- **Tracing** (`agents/tracing.py:traced_run`) — times one `Agent.run()` call and logs a single `"agent_execution"` structured event (`status`/`latency_ms`/`prompt_tokens`/`completion_tokens`), wired into the orchestrator's two real per-agent call sites. Token fields stay honestly `None` until an agent's output is a real `LLMResponse` — no agent produces one yet.
- **Parallel execution** (`agents/parallel.py:run_parallel`/`gather_partial`) — runs independent `(agent, input)` steps concurrently via `asyncio.gather`, each still traced individually; `gather_partial` returns one `ok`/`failed` result per step instead of failing the whole batch. Real, tested (including a wall-clock timing proof of genuine concurrency), not yet wired into the orchestrator — `PlanningAgent` only ever plans one agent (`["retriever"]`) today, so there's no real multi-independent-agent request yet to parallelize.
- **Failure handling** (`agents/resilience.py:with_retry`/`with_fallback`) — linear-backoff retry and primary/fallback agent substitution, both tracing every attempt. No retry library added; this codebase's only other retry precedent (Celery's `autoretry_for`, the document pipeline) only applies to background tasks, not inline request-path agent calls.

### Assistants

`Assistant` (`models/assistant.py`) is the product-facing configuration surface — one level under `KnowledgeBase` in the tenant hierarchy (`Organization → Workspace → KnowledgeBase → Assistant`), with `name`/`slug`/`description` plus an `agent_configuration` JSONB column. That column stores `agents/configuration.py:AgentConfiguration`, a validated Pydantic model built specifically to give it a real shape: `llm_provider` validated against `llm.PROVIDERS`' live keys, `enabled_agents` validated against each real agent's own `.name` (deliberately excluding the two ingestion-time agents, which are never part of an assistant's runtime request path), `retrieval_top_k` bounded to `RetrieverAgent`'s own real parameter. `routers/assistant.py` exposes create/list/get/delete, nested under `.../knowledge-bases/{id}/assistants`, validating `agent_configuration` at the API boundary before it ever reaches the JSONB column — no update endpoint, matching `KnowledgeBase`/`Workspace`'s own CRUD scope.

**Honest, tracked gaps, not silently worked around:**
- No agent calls an LLM provider yet — `ReasoningAgent`/`ConversationAgent`/`QualityReviewAgent`/`SafetyAgent` are real classes with no implementation, waiting on infrastructure Milestone 6 builds (conversation/session models, a real chat model to reason/converse/review/guard with).
- `PlanningAgent` is a deterministic two-branch heuristic, not an LLM-based planner — no chat model exists yet to plan with.
- `agents/parallel.py:run_parallel`/`gather_partial` are real and tested but not wired into the orchestrator — no request today plans more than one independent agent.
- `AgentRegistry` is real and tested but empty at runtime — nothing constructs-and-registers agents at app startup, since no router depends on registry lookup yet.
- `Assistant` has no update endpoint — only create/list/get/delete exist, matching every other resource at this layer.

## Memory architecture

Two genuinely separate stores, not two modes of one abstraction — "Memory is different from retrieval. Do not mix them" (AGENTS.md), and short-term and long-term memory are different from *each other* too: short-term never touches Postgres, long-term never touches Redis, and the only bridge between them is a real decision, not automatic promotion.

### Short-term memory

`short_term_memory.py` — a Redis LIST per conversation (`session_id`), storing real `llm.base.Message` entries (role/content, the exact shape a chat call needs). `append_turn` pushes and trims to `MAX_ENTRIES` (50); every write refreshes a one-hour TTL, so an idle conversation's working memory expires on its own. No `Conversation`/`ConversationSession` model exists yet (Milestone 6) — `session_id` is an opaque, caller-supplied UUID today, the same identifier `models/memory.py:Memory.session_id` uses for its own unconstrained reference.

### Long-term memory

`models/memory.py:Memory` — Postgres, tenant-scoped, RLS-protected. Three real scopes (`scope` column): **user** (`user_id`, a real FK — one person's preferences/history), **organization** (no extra column; `tenant_id` already identifies it — shared business context), **session** (`session_id`, unconstrained — same reason as the Redis store). `memory_type` genuinely supports `"short_term"`/`"long_term"` as values, but only `"long_term"` is ever written here — short-term entries never get promoted into a row automatically. `importance_score` (0.0–1.0, app-level convention) drives everything downstream: retrieval ordering, expiration duration, and conflict resolution all read the same number rather than three independently invented scales.

`repositories/memory.py:MemoryRepository` is the real access layer: `list_for_user`/`list_for_organization`/`list_for_session` (importance-ordered, already-expired rows excluded), `list_all_for_user`/`delete_all_for_user` (the export/erasure pair, deliberately unfiltered by expiration or importance — both are "give me *everything*" operations), and `update_content` (the one real update path, used only by conflict resolution).

### The retention decision

`agents/memory.py:MemoryAgent` is the first Milestone-4 skeleton to gain real logic: `run(Message) -> RetentionDecision` is a deterministic heuristic — no LLM judges this — scoring on content length and explicit identity/preference signal phrases ("my name is", "remember that", ...). Below `RETENTION_THRESHOLD` (0.5), content is never written to Postgres at all; "not every conversation should become permanent memory" is enforced at the point of creation, not cleaned up after the fact.

### The summarization pipeline

`memory_summarization.py:dispatch_memory_summarization` (Celery, same task shape as the document pipeline's own background jobs) is the one real path that turns short-term memory into long-term memory, and the first code in this codebase to call a real LLM provider directly (`llm/openai.py:OpenAIProvider`, not through an agent — summarization isn't an `Agent.run()`-shaped decision). Per dispatch: read a session's Redis turns → summarize via a real LLM call → run the summary through `MemoryAgent`'s own retention decision → check `memory_conflict.py:find_conflicting_memory` (a word-overlap heuristic, not embeddings — `Memory` has no embedding column) against the session's existing memories → **create** a new row, **update** a conflicting one that it outscores, or **ignore** it entirely → clear the Redis turns either way. Every real outcome is logged via `memory_observability.py:log_memory_event` (one structured event, an `outcome` field: created/updated/ignored), so an operator can see not just *that* something happened but *why*.

### Expiration and conflict resolution

`memory_policy.py:compute_expiration` maps `importance_score` to a real TTL — permanent above 0.8, 90 days above the retention threshold, 7 days below it (a defensive floor `MemoryAgent`'s own output never actually reaches). `expire_stale_memories` is a real, dispatchable Celery task, explicitly **not** a scheduled job — this codebase never adds Celery Beat, matching the same "build the task, not speculative scheduling infra" choice the document pipeline's own maintenance task made. Between when a memory expires and when that task next runs, the row still physically exists; `MemoryRepository`'s own retrieval methods exclude it anyway, so expiration is enforced at read time regardless of when the sweep gets around to deleting it.

### Privacy and identity-based retrieval

`memory_retrieval.py:retrieve_memory_for_conversation_start` combines a user's own memory with their organization's shared memory into one importance-ordered result — the real substance behind "the assistant should feel continuous rather than stateless." `routers/memory.py` gives users real, self-service control over their own data: view, export (everything, unfiltered), and two distinct deletion operations — a granular per-entry delete and a comprehensive right-to-erasure that wipes every user-scoped memory at once, audit-logged since a bulk erasure is exactly the kind of event `AuditLog` exists for.

**Honest, tracked gaps, not silently worked around:**
- No agent calls an LLM provider through the `Agent.run()` contract yet — `memory_summarization.py` calls `OpenAIProvider` directly, matching the embedding pipeline's own precedent for provider calls outside the agent abstraction.
- Right-to-erasure doesn't reach into Redis short-term memory — there's no `user_id → session_id` mapping anywhere in this codebase yet (that needs Milestone 6's `Conversation` model); short-term memory's own one-hour TTL is the only real cleanup for it today.
- Conflict resolution is word-overlap, not semantic similarity — `Memory` has no embedding column, and adding one wasn't asked for by this milestone's own roadmap wording.
- `memory_type="short_term"` and the `"updated"` observability outcome are both real, callable values nothing in this codebase currently produces — short-term memory never gets a Postgres row, and nothing but conflict resolution ever updates one.

## Conversation engine

Two genuinely separate entry points into the same real message-send/citation/streaming machinery — an **authenticated** flow (a real member of an org talking to their own assistants) and an **anonymous** one (a pre-auth visitor, the shape a real embeddable widget needs) — plus a client (`apps/web`) that, for now, can only honestly reach the anonymous door, since no authenticated dashboard UI exists yet.

### Conversation & message model

`models/conversation.py:Conversation` — tenant-scoped, `assistant_id` (required), `user_id` (nullable — `NULL` means anonymous, the same flag both flows share), `status`, `title`/`is_pinned`. `models/message.py:Message` — `role`/`content` mirroring `llm/base.py:Message`'s own field names, plus `citations` (JSONB), `feedback_type` (nullable), `embedding` (pgvector) and a DB-`Computed` `search_vector` (tsvector) for the two message-search mechanisms below. `conversation_state.py` is a real, small state machine (`VALID_TRANSITIONS` dict graph over `new`/`active`/`waiting`/`processing`/`completed`/`archived`) — only `new → active` (first message sent) and `→ archived` are ever triggered by real code today; the others are legal, real states with no caller that needs them yet.

### Message-send flow

`message_processing.py:generate_assistant_reply` is the one real "process a turn" function both flows call: transitions `new → active`, persists the user's `Message`, calls `orchestrator.handle()` (Milestone 4 — keyword-only retrieval today, no OPENAI_API_KEY in this environment; the response is the retrieved chunks' own raw text, or `"No results found."`, not an LLM-synthesized answer, since no chat/generation model exists yet), builds real `citations.py:Citation` objects from whichever chunks fed the response, persists the assistant's `Message`, and dispatches embedding computation (`message_embedding.py`, Celery) for both turns. Deliberately does **not** thread prior conversation turns into `orchestrator.handle()` — that signature stays single-query-in/single-response-out, the same discipline that kept Milestone 4's other signatures narrow until a real caller needed more. `message_rendering.py:render_markdown` (Python-Markdown + `nh3` sanitization) renders `Message.content` to safe HTML on every read (`MessageRead.content_html`, a Pydantic `computed_field`, never stored) — a real, live-confirmed XSS surface (`nh3` was needed after finding a raw `<script>` survives unrendered) closed at the point of serving, not the point of storage.

### Streaming

`POST .../messages/stream` (both flows have one) returns real, incremental `text/event-stream` — word-chunked `event: message` frames plus a terminal `event: done` carrying the fully-persisted `MessageRead`. Honest about what's actually streamed: `orchestrator.handle()` still computes the whole response before the first byte is sent (no roadmap step through 300 asks for token-level generation streaming); this is real transport a future token-streaming source can plug into unchanged. `message_processing.py:build_message_stream` is the one shared generator both routers' streaming endpoints use — reads only from an already-validated `MessageRead`, never the ORM object, since the request-scoped session commits (and expires every tracked attribute) the instant the endpoint function returns, before Starlette starts iterating the response body.

### Anonymous access (embeddable-widget channel)

`routers/public_conversation.py` is a genuinely separate router, not a content-negotiated branch of the authenticated one — keyed by `assistant_id` alone (`/public/assistants/{assistant_id}/...`), the one identifier a real `<script data-assistant-id="...">` embed tag can carry. Public reachability is opt-in per assistant (`Assistant.is_public`, default `False`), checked against a narrowly-scoped permissive RLS policy (`assistant_by_id`) that only exposes enough of the row to check that flag before any tenant context exists. Ownership of an anonymous `Conversation` (`user_id IS NULL`) is proven by a signed JWT (`type "anonymous_session"`, rejected by the normal access-token decoder outright) scoped to exactly one `conversation_id` — there is no account behind it, only "you are whoever started this specific conversation."

### Identity-triggered memory reconnection

`POST .../conversations/claim` (authenticated only) lets a newly-signed-in caller present an anonymous session token, transfer that conversation's ownership to their real account, and receive their own relevant long-term memory (`memory_retrieval.py:retrieve_memory_for_conversation_start`, built in Milestone 5, unreachable by any real caller until this endpoint) directly in the response — a client-facing capability, not something silently injected into generation, since no chat UI yet consumes a prompt-engineered version of it.

### Message search

Two separate mechanisms, not one endpoint with a mode flag — mirroring Milestone 3's own dense/keyword/hybrid split precedent: keyword (Postgres full-text over `search_vector`) works in every environment; semantic (cosine similarity over `embedding`) needs a real `OPENAI_API_KEY`, absent in this environment, and fails closed with a clean 500. Both are scoped to the caller's own conversations for a given assistant — reachable only through the authenticated router, since "my conversations" has no meaning for an anonymous caller.

### Rate limiting

`rate_limit.py:check_rate_limit` — the same real Redis fixed-window logic Milestone 2's per-IP auth-route limiter already used, generalized to any string key. Message-send on *both* doors shares one Redis-backed budget keyed by `tenant_id` (60/minute) — the real cost being protected (an LLM call through `orchestrator.handle()`) is identical regardless of which door a message came through, and the anonymous door is the more abuse-prone of the two (zero signup friction).

### Frontend (`apps/web`)

A real `/chat?assistantId=<id>` page — message list, input, a genuine SSE-consuming streaming render, a typing indicator for the pre-first-chunk gap, a conversation sidebar, and client-side conversation search. Deliberately talks only to the **anonymous** door: no authenticated dashboard/login UI exists yet (Milestone 9's own admin dashboard, steps 233+, is what eventually reaches the authenticated conversation endpoints from a browser). Conversation history and search are therefore genuinely client-side — a localStorage-backed store (`lib/conversationStore.ts`) scoped per assistant, holding each conversation's full message list so switching between them needs no backend re-fetch — "your recent chats on this device," the same pattern real embeddable widgets already use for anonymous visitors, not a stand-in for the authenticated dashboard's own future server-backed history. The one Playwright e2e test (`e2e/chat.spec.ts`) provisions its own real org/workspace/knowledge-base/public-assistant via direct HTTP calls and asserts on the real SSE response (multiple `event: message` chunks, not one blob) alongside the rendered UI — nothing mocked.

**Honest, tracked gaps, not silently worked around:**
- No LLM synthesizes a response — a real hit's "response" is the retrieved chunks' own raw text, or a literal "No results found."; `ConversationAgent`/`ReasoningAgent`/`QualityReviewAgent`/`SafetyAgent` are still real classes with no implementation, waiting on a real chat/generation model this milestone never needed to add.
- No conversation history is threaded into generation — every turn is independent from the orchestrator's own point of view; a user's prior messages exist in Postgres but are never read back into a prompt, since there is no prompt yet.
- Streaming is real transport, not real token-level generation streaming — the whole response is computed before the first SSE byte goes out.
- Message-history search (`search_keyword`/`search_semantic`) and the frontend's own client-side conversation search are two unrelated mechanisms with no shared code — the former needs a real authenticated caller apps/web can't produce yet.
- The chat UI shell has no authenticated mode — it cannot reach a user's own real conversation history (`list_conversations`) or the claim endpoint until Milestone 9's dashboard exists to authenticate through.

## Embeddable widget

`apps/widget` — vanilla TypeScript, zero framework (ADR-0001), bundled to a single minified IIFE (`esbuild`) a customer loads via one `<script>` tag. Deliberately talks only to the conversation engine's [anonymous door](#anonymous-access-embeddable-widget-channel) — the same public router `apps/web`'s own chat page uses, not a separate integration.

### Config and mounting

`src/config.ts:loadWidgetConfig` reads the embed `<script>` tag's own `data-*` attributes (`document.currentScript`, falling back to `querySelector('script[data-assistant-id]')` for async/deferred embeds) — `data-assistant-id` is the one required identifier; org/workspace/knowledge base are all resolved server-side from it. `src/launcher.ts:mountLauncher` mounts into a real Shadow DOM root (`attachShadow({mode:"open"})`, `:host{all:initial}`) for genuine CSS isolation from whatever host page it's dropped into — a hard requirement for this product class, not speculative isolation. Theme (`primaryColor`/`fontFamily`/`logoUrl`/`position`/`colorScheme`) is real CSS custom properties set via `host.style.setProperty()`, safe against a customer-supplied value being used to break out into new CSS. `src/chat-window.ts:renderChatWindow` is the vanilla-DOM functional equivalent of `apps/web`'s own React `ChatShell`/`MessageList` — same message list/streaming/citation behavior, sharing wire-format types and the anonymous-conversation API client with `apps/web` through `packages/shared` (promoted there once `apps/widget` became a second real consumer, not built shared from the start).

### Theming and responsiveness

Dark/light mode (`colorScheme: "auto"|"light"|"dark"`) follows the visitor's real `prefers-color-scheme` by default; only structural surfaces (panel/bubbles/borders) change, the customer's own brand `primaryColor` stays identical in both modes. Below a 480px viewport the panel switches to a real full-screen layout — the same pattern Intercom/Drift-class products already use, since the normal fixed 360×480 corner panel would overflow a real phone screen.

### Deployment and distribution

`.github/workflows/widget-deploy.yml` (`workflow_dispatch`, a deliberate release action, not continuous deploy) builds the bundle and publishes it to GitHub Pages — genuinely Fastly-CDN-backed (confirmed via real response headers, not assumed), needing no new cloud account this project doesn't already have. `scripts/assemble-pages-artifact.mjs` works around Pages' full-content-replace-per-deploy behavior: it fetches every prior version a `versions.json` manifest already lists and re-publishes them alongside the new one, so `widget.js` (root) always serves latest while `v{version}/widget.js` stays a permanent pinned URL for any customer who wants one. `scripts/check-bundle-size.mjs` fails CI if the built bundle exceeds a 30 KB raw budget (real bundle is ~10 KB as of this writing).

### Testing

`e2e/widget.spec.ts` (Playwright) is a real, unmocked smoke test: a real browser loads the real built bundle on a real static fixture host page (`e2e/fixtures/host-page.html`), opens the launcher (Playwright locators pierce open Shadow DOM automatically), and sends a real message through a real running `apps/api` instance the CI job provisions itself.

**Honest, tracked gaps, not silently worked around:**
- No dashboard UI exists yet to generate/copy an embed snippet for a customer — `apps/web/lib/embedCode.ts:generateEmbedCode` is real and tested (`e2e/embedCode.spec.ts`) but has no caller until Milestone 9's dashboard (step 233+).
- No custom greeting message, animation customization, i18n/language selection, or arbitrary custom-CSS injection — AGENTS.md's own customization list names all of these; only theme (color/font/logo/position/color-scheme) is implemented.
- Same generation gap the conversation engine has generally: a real hit's response is the retrieved knowledge-base text itself, or "No results found." — no LLM synthesizes it.
- The GitHub Pages CDN URL is a real, live, working deployment, but a personal-repo URL — not the permanent production domain a real customer-facing default should eventually point at (Milestone 11's infrastructure work).

Full customer-facing setup instructions (the embed snippet, every `data-*` attribute, domain restriction, version pinning) live in [`docs/embedding.md`](embedding.md), not duplicated here.

## Voice platform

Real audio in, real speech back out, sharing the SAME conversation intelligence the text-chat door already built (Milestone 6) — not a parallel bot. Built on the anonymous-session router (`routers/public_conversation.py`) the widget already uses: a caller first gets an anonymous conversation + token the normal text-chat way, then starts a voice session under it, so a call is authorized by the identical mechanism as a typed message and can pick up an existing text thread mid-conversation (or vice versa).

### Provider abstraction

`voice/base.py` — two structural `Protocol`s, `SpeechToTextProvider`/`TextToSpeechProvider`, the same "interface lands before any concrete implementation" precedent `llm/base.py`/`embeddings/base.py` already established. Deliberately non-streaming at this layer (`bytes` in, one result out) — the streaming behavior lives one level up, in the websocket route, not in the provider contract itself. `voice/whisper.py:WhisperSTTProvider` and `voice/openai_tts.py:OpenAITTSProvider` are the only concrete implementations (`whisper-1` / `tts-1`, OpenAI); no `PROVIDERS` registry exists yet, matching this codebase's own "don't build the registry before there's a real second entry to put in it" rule (`llm/__init__.py`'s own history). Both raise a single `SpeechProviderError` on any real failure (auth, rate limit, network, malformed audio) — one thing every caller catches, regardless of which provider is behind it.

### Data model

`models/voice_session.py:VoiceSession` — tenant-scoped, one level under `Conversation` the same way `Message` already sits under it, `ended_at` (nullable — live vs. closed) the only lifecycle field. No unique constraint on `conversation_id`: one conversation can span multiple real voice calls over time, or mix voice and text turns. A finished voice turn becomes an ordinary `Message` row through the exact same `message_processing.py:generate_assistant_reply` pipeline text chat uses — `Message.voice_session_id` (nullable FK, `SET NULL` on delete) is the precise, queryable link, not a `created_at` time-window approximation.

### Lifecycle endpoints (REST)

`POST .../conversations/{id}/voice-sessions` and `POST .../voice-sessions/{id}/end` (`routers/public_conversation.py`) open and close a session, reusing the router's existing `AnonymousConversation` dependency wholesale rather than a second auth path. Ending a session is idempotent-409 on a repeat call, and its response includes the session's own exact transcript (`repositories/message.py:list_for_voice_session`, reusing `MessageRead`) — the same "don't invent a parallel response shape for the same data" precedent `ConversationExportRead` already set for text chat's export endpoint.

### The audio WebSocket

`routers/public_voice.py`, `WS /public/assistants/{id}/voice-sessions/{id}/audio` — this codebase's first and only websocket route, and a genuinely different code shape from every REST endpoint in this project for one real reason: `errors.py:register_exception_handlers` only intercepts HTTP request exceptions, never websocket connections, so a `Depends()`-raised error inside a websocket route gets no graceful handling. `_authenticate` therefore does its own inline resolution — first-message JSON handshake (`{"token", "mime_type"}`, not a URL query param, so it never lands in browser history or proxy logs), decoding the same anonymous-session JWT the REST doors use, then re-checking the target `VoiceSession` under the URL's own tenant context — closing with a real WS close code (1008 Policy Violation) and reason string on any failure, the websocket-native equivalent of a 401/404. Binary frames are buffered client audio; `{"type": "end_turn"}` (explicit push-to-talk) or one of two automatic detectors finalizes a turn:
- **Silence timeout** (`SILENCE_TIMEOUT_SECONDS`, 1.5s) — no further audio within the window once a turn has started.
- **Content-size VAD** (`_voice_activity_has_stopped`) — several consecutive recent chunks all much smaller than the turn's own peak. A real, dependency-free heuristic leveraging Opus/webm's own variable-bitrate encoding (silence compresses smaller even undecoded) — explicitly **not** real acoustic/PCM-level VAD, which would need a new codec/ffmpeg dependency this milestone never needed.

A finalized turn calls `WhisperSTTProvider.transcribe`, sends `{"type": "transcript", ...}`, then — the same real orchestrator call text chat uses — `generate_assistant_reply` (passing `voice_session_id` so both the user's and assistant's `Message` rows land under this call), sends `{"type": "reply", "text", "citations"}`, and speaks it via `_stream_synthesis` — `OpenAITTSProvider.synthesize` run as a background `asyncio.Task` (not awaited inline), streamed back as 4 KB binary frames terminated by `{"type": "synthesis_done"}`. Running synthesis as a decoupled task is what makes real **barge-in** possible: any new client message while synthesis is in flight — including the silence-timeout path finalizing a new turn with nothing else to signal it — cancels the task and sends `{"type": "interrupted"}`, matching how barge-in actually works in a real voice UX (new speech IS the interrupt signal). An explicit `{"type": "interrupt"}` control message rides the same path for a client-initiated stop with no new audio.

`voice/tracing.py` logs two separate real structured latency events per turn: `log_turn_processing` (STT through reply generation — the real time a caller waits in silence) and `log_synthesis` (TTS latency, with a genuine third `status="interrupted"` outcome distinct from success/failure, since conflating a barge-in with a slow call would make the numbers meaningless). `voice/benchmark.py` (`python -m voice.benchmark`) is a standalone, non-CI-gated measurement script — a real TTS→STT round trip over a small fixture set, reporting real latency plus a real quality signal (how closely Whisper's own transcription matches the known input text, via `difflib` similarity) — deliberately not a hard pass/fail gate, since every voice provider here is OpenAI-backed and there's no environment-independent path (unlike keyword search on the retrieval side) to assert a threshold against.

### Tenant isolation

Same defense-in-depth as every other tenant-scoped subsystem: Postgres RLS on `voice_sessions`, plus app-layer checks at all three real entry points. `tests/test_voice_tenant_isolation.py` is the dedicated proof, including the websocket's own strongest case — an attacker's genuinely valid token for their OWN tenant, pointed at another tenant's real `assistant_id` and real `voice_session_id` (not a guessed/random id): `VoiceSessionRepository.get` actually finds a real row under the target tenant's context, so only the `conversation_id`-ownership check inside `_authenticate` is what stops the attempt, not RLS returning nothing outright.

### Widget UI (`apps/widget`)

`src/voice.ts:VoiceSession` is the client half of the same protocol — a real `MediaRecorder` for capture (`audio/webm`, the one codec every real Chromium/Firefox `MediaRecorder` supports without an explicit codec string), a real `AnalyserNode` for a live RMS level signal driving a canvas waveform, one websocket connection for the widget's whole session lifetime (matching `VoiceSession`'s own server-side "one session, many turns" design), and `stopRecording()` sending a real `{"type":"end_turn"}` only after `MediaRecorder.stop()`'s own final `dataavailable` event has already queued the last audio chunk. `chat-window.ts` wires a push-to-talk mic button and the waveform into the existing chat panel, reusing the same message-list rendering for voice transcripts and replies. Teardown on page unload uses `fetch(..., {keepalive: true})`, not `navigator.sendBeacon` — sendBeacon cannot carry the custom `Authorization` header this app's anonymous-session auth model requires.

**Honest, tracked gaps, not silently worked around:**
- No real `OPENAI_API_KEY` exists in this project's local dev/CI environment — every live-verification of STT/TTS in this milestone confirmed the honest fail-closed path (a clean `SpeechProviderError`, zero partial state persisted), not a real successful transcription/synthesis; `voice/benchmark.py` reports this plainly (0% success) rather than faking a number.
- Content-size VAD is a real, legitimate proxy, not real acoustic/PCM-level voice-activity detection — a client sending audio at a perfectly steady bitrate regardless of actual speech would defeat it (the silence-timeout fallback still catches that case).
- Safari's `MediaRecorder` needs an explicit `"audio/mp4"` `mimeType` this widget doesn't send (`audio/webm` is hardcoded) — no roadmap step through 232 asked for cross-browser codec negotiation; this is a known, real gap on Safari/iOS specifically.
- No dashboard UI exists to configure a per-assistant voice (TTS voice selection, STT language hint, enable/disable voice entirely) — Milestone 9's admin dashboard is the real future home for that, the same gap the embeddable-widget section above already notes for its own embed-snippet UI.
- `ConversationAgent`/`ReasoningAgent`/`QualityReviewAgent`/`SafetyAgent` still have no implementation — a voice turn's "reply" is exactly as generation-free as a text turn's (retrieved-chunk text or `"No results found."`), inheriting the conversation engine's own honest gap rather than adding a new one.

## Security architecture

_Milestone 10 (steps 251–266) is complete — this section documents it in full, step by step._

**Prompt injection defense (step 251).** `agents/safety.py:SafetyAgent` wraps retrieved/prior-turn content in explicit `<retrieved_content>` delimiter tags before it reaches a real LLM call, paired with a matching system-prompt instruction that content inside those tags is data, never an instruction to obey. Applied at both real LLM call sites this codebase has (`follow_up_questions.py`, `memory_summarization.py`).

**API input/output validation (step 252).** Every route's request body and success response resolves to a real, named Pydantic schema — no raw `dict`/`Any` passthrough. Enforced as a standing regression test (`tests/test_api_schema_validation.py`), which introspects the app's own generated OpenAPI schema rather than trusting route decorators to stay correct by convention.

**Secrets management (step 253).** Environment variables, centralized through one typed `config.py:Settings` object — no scattered `os.environ.get()` calls. Full rationale, the real current secrets inventory, and the migration path to a dedicated vault if this project ever needs one: [`docs/adr/0004-secrets-management.md`](adr/0004-secrets-management.md).

**Encryption at rest (step 254).** Audited every model in `models/__init__.py`'s own canonical registry — every credential-shaped column already hashes (passwords, backup codes, refresh tokens, API keys, invitation/verification tokens) or Fernet-encrypts (MFA TOTP secrets, which unlike a password must stay recoverable) its real value before storage; no plaintext secret column exists anywhere in the schema. Enforced as a standing regression test (`tests/test_sensitive_column_encryption.py`) that scans every real column name for credential-shaped tokens (password/secret/token/credential/key) and fails unless it's hashed, encrypted, or a reviewed, individually-justified exception (e.g. `Document.storage_key`, an object-storage path, not a secret).

**Security event audit logging (step 255).** Permission denials and cross-tenant access attempts each write a real `AuditLog` row (`security.permission_denied`, `security.cross_tenant_attempt`) inside the same transaction the check itself ran in — a cross-tenant attempt is attributed to the org that was *targeted*, so its own admins see it through the existing audit-log viewer. Failed logins have no tenant context yet, so they log a structured `login_failed` event instead.

**Distributed tracing (step 256).** OpenTelemetry instruments FastAPI, Celery (both dispatch and execution sides), and SQLAlchemy, with a distinct `service.name` per process (`agentforge-api` / `agentforge-worker`). Gated by an empty-by-default `OTEL_EXPORTER_OTLP_ENDPOINT` — real, tested code that's genuinely inert until a real collector is configured.

**Metrics export (step 257).** `GET /metrics` on the API exposes Prometheus-format HTTP request counters/histograms labeled by route pattern. The Celery worker process has no web server of its own, so it exposes its own task counters on a second, dedicated port (`WORKER_METRICS_PORT`) via `prometheus_client.start_http_server()` — a real deployment scrapes both as separate jobs.

**Error tracking (step 258).** `sentry-sdk` wired into both processes, gated by an empty-by-default `SENTRY_DSN`. No explicit `capture_exception()` calls anywhere — the installed integrations (`FastApiIntegration`, `StarletteIntegration`, `CeleryIntegration`) correctly capture real unhandled exceptions and task failures while correctly *not* capturing expected `AppError` 4xx responses, which each have their own specific registered handler.

**Rate limiting & abuse detection (step 259).** Redis-backed fixed-window limiting, per-client-IP for auth routes and per-tenant for message-send/document-upload/search (one shared budget per real underlying cost, not per route). A separate, distinct signal — `record_failed_login_attempt` — tracks failed logins per *email* (not per IP), catching a slow, distributed credential-stuffing attempt that stays under the per-IP cap; it only logs, it never blocks.

**Dependency & static-analysis scanning (steps 260–261).** CI runs `pip-audit` (apps/api) and `pnpm audit` (apps/web + apps/widget) against the real locked dependency sets, plus GitHub CodeQL (Python and JavaScript/TypeScript) — all on push/PR and a weekly cron, so a newly-published advisory against already-merged code still gets caught.

**Security test suite (step 262).** `tests/test_security_suite.py` — HTTP-level auth-bypass tests (missing/malformed/forged/expired tokens, including a live-verified alg=none forgery attempt) and SQL-injection-shaped payload tests. Cross-tenant access and RBAC already had extensive dedicated coverage elsewhere (RLS-level isolation tests, per-endpoint tests, the audit-log tests above) — not duplicated, only referenced.

**Incident-response runbook (step 263).** [`docs/runbooks/incident-response.md`](runbooks/incident-response.md) — grounded in the real architecture as it exists today rather than speculative production infra, with real, per-failure-type diagnostic playbooks pointing at the surfaces above (`GET /system-health`, `GET /metrics`, `AuditLog`, the security test suite) and an honest "Known gaps" section rather than pretending everything's covered.

**Responsible disclosure policy (step 264).** [`SECURITY.md`](../SECURITY.md) at the repo root, backed by GitHub's own private vulnerability reporting (enabled for this repo as part of this step, not just documented) as the preferred report channel, with email as a fallback.

**Backup automation + restore-drill (step 265).** `scripts/backup.sh` (real `pg_dump` of Postgres + a tarball of MinIO's data) and `scripts/restore-drill.sh`, which restores a specific backup into a throwaway container and verifies real, queryable data comes back — proving a backup is actually restorable, not just that a dump file exists. `make backup` / `make restore-drill BACKUP=...`.

### Summary

Ten steps, three shapes of work: from-scratch implementation where a real gap existed (251, 255–259, 262, 265), audits that confirmed already-correct behavior and turned it into a permanent regression test (252, 254), and documentation that's honest about what's real today versus what Milestone 11 (deployment infra) will need to add (263, 264, 266 — this section itself). The throughline every step shares: live verification over assumption — a real curl loop, a real forged token, a real restore into a real throwaway container — and naming gaps explicitly (no backup schedule yet, no production deployment yet, no region redundancy yet) rather than implying more coverage than actually exists.

## Infrastructure & deployment

_Milestone 11 (steps 267–280) is in progress — this section grows as each step lands._

**Production Dockerfiles (step 267).** `apps/api/Dockerfile` and `apps/web/Dockerfile` — multi-stage, non-root `app` user, real healthchecks. Both existed since much earlier in this project's history but had zero CI coverage until this step; [`.github/workflows/docker-build.yml`](../.github/workflows/docker-build.yml) now builds and smoke-tests both on every push/PR. `apps/widget` deploys as a static bundle to a CDN (step 209/210) and correctly has no Dockerfile of its own.

**Reference deployment (step 268).** [`docker-compose.prod.yml`](../docker-compose.prod.yml) — a real, single-host production stack (the two Dockerfiles above plus the existing infra services), real secrets via `.env.prod` (template: [`.env.prod.example`](../.env.prod.example)), `ENVIRONMENT=production` so `config.py`'s own placeholder-secret validator enforces real secrets at startup.

**Self-hosted deployment documentation (step 269).** [`docs/self-hosted-deployment.md`](self-hosted-deployment.md) — every command in it was actually run against this stack, including the two real bugs step 268 caught live (a broken worker startup command, and a Next.js build-time-vs-runtime env var that would have silently shipped every deployment pointed at `localhost`).

**CI/CD image publishing (step 270).** [`.github/workflows/docker-build.yml`](../.github/workflows/docker-build.yml) pushes `api`/`web` images to GHCR (`ghcr.io/ahmedirfan7/...`) on every real push to main (never a PR). Confirmed live end to end, including an independent, unauthenticated `docker pull` from this machine — the images are genuinely public and pullable, not just "the CI step exited 0."

**Staging deploy workflow (step 271).** [`.github/workflows/staging-deploy.yml`](../.github/workflows/staging-deploy.yml) — real and correct, `workflow_dispatch`-triggered SSH deploy using the exact same `docker-compose.prod.yml` commands a human operator would run by hand, honestly waiting on `STAGING_HOST`/`STAGING_SSH_USER`/`STAGING_SSH_KEY`/`STAGING_DEPLOY_PATH` secrets this project doesn't have yet (no real staging host exists — AGENTS.md's own "CONTINUOUS DELIVERY" section names "Future deployment automation" as future, not built). `docker-compose.prod.yml`'s own `api`/`worker` services now carry both `build:` and an `image:` default pointing at the GHCR tag step 270 publishes — the same file supports both "build from source locally" (self-hosted) and "pull the CI-built image" (staging) without duplicating service definitions across two files.

**Production deploy workflow with manual approval gate (step 272).** [`.github/workflows/production-deploy.yml`](../.github/workflows/production-deploy.yml) — same real shape as staging's own deploy workflow, targeting a separate `production` GitHub Environment with its own separate secrets (`PRODUCTION_HOST`/etc., distinct from staging's). The "manual approval gate" is GitHub's own real, native Environment protection rule (`required_reviewers`), configured directly via the API on the repo's `production` environment — confirmed live via `gh api repos/.../environments/production`, not simulated in the workflow YAML itself. A `workflow_dispatch` run genuinely pauses for a real reviewer's approval before any deploy step executes.

**Health-check + readiness probes (step 273).** `GET /health` stays a cheap, dependency-free pure liveness check (used by both Dockerfiles' own `HEALTHCHECK` directives); new `GET /ready` does real Postgres + Redis checks and returns 503 if either fails, for a reverse proxy to route around an instance that can't actually serve a request without killing it the way a failed liveness check would.

**Horizontal scaling (step 274).** No architectural change needed — auth is stateless (JWTs, no server-side session store), tenant isolation is enforced in Postgres itself (RLS) rather than per-process state, and Celery workers already scale horizontally by design (step 089). `docker compose ... --scale api=N --scale worker=M` is real and documented in [`docs/self-hosted-deployment.md`](self-hosted-deployment.md#horizontal-scaling), including a live-verified confirmation that Docker Compose's own embedded DNS round-robins across replicas with no extra load-balancer config, and the one real caveat scaling actually requires (removing `api`'s own fixed host port once a reverse proxy is in place).

**CDN config for widget assets (step 275).** The widget bundle already deploys to a genuine CDN (GitHub Pages, step 209/210) — confirmed live (`curl -I` against the real deployed URL) that GitHub Pages has no configuration surface for its own `Cache-Control` headers at all: every file gets a fixed `max-age=600`, whether it's the mutable auto-updating `widget.js` or an immutable pinned `v{version}/widget.js`. The real, addable hardening within that actual platform constraint: `apps/widget/scripts/assemble-pages-artifact.mjs` now publishes a real SHA-384 Subresource Integrity hash for every pinned version in `versions.json`, letting a customer's browser cache and verify a pinned version far more aggressively than the origin's short cache header alone allows — documented in [`docs/embedding.md`](embedding.md#pinning-a-specific-widget-version). Real backward-compatibility bug caught by actually running the updated script against the live site (not assumed): the real currently-deployed `versions.json` was still the pre-step-275 flat-array shape, and naively calling `Object.keys()` on an array returns numeric indices, not version strings — fixed with an explicit `Array.isArray()` migration path, and every SRI hash is computed from the actually-fetched bytes rather than trusted from any stored value.

**Environment-config documentation (step 276).** [`docs/environment-variables.md`](environment-variables.md) — every one of `config.py:Settings`' own 32 real fields, in one indexed table, generated by reading that class in full rather than re-derived from memory. An index, not a duplicate source of truth: each variable's own full rationale still lives in `config.py`'s own inline comments or whichever real `.env*.example` file it came from.

## Related documents

- [`docs/ROADMAP.md`](ROADMAP.md) — the 300-step implementation plan
- [`docs/adr/`](adr/) — Architecture Decision Records
- [`docs/runbooks/incident-response.md`](runbooks/incident-response.md) — what to do when something real breaks
- [`docs/self-hosted-deployment.md`](self-hosted-deployment.md) — how to actually run this in production on one host
- [`docs/environment-variables.md`](environment-variables.md) — every real env var this project reads, in one place
- [`SECURITY.md`](../SECURITY.md) — responsible disclosure policy
- [`docs/embedding.md`](embedding.md) — customer-facing widget embedding guide
- [`AGENTS.md`](../AGENTS.md) — the project's full engineering constitution
