# AgentForge Architecture

This document describes the system **as implemented**, not as aspired to — it grows one section at a time as each subsystem lands, per the checkpoints built into `docs/ROADMAP.md`. For the full product/engineering vision this architecture serves, see [`AGENTS.md`](../AGENTS.md). For why specific technologies were chosen, see [`docs/adr/`](adr/).

## Status

Milestone 3 (Knowledge Pipeline: Ingestion + RAG) complete; Milestone 4 (Agent System) next. Sections below are filled in as the corresponding roadmap milestone completes — an empty section means that subsystem doesn't exist yet, not that it was forgotten. (Authentication & authorization, Milestone 2, is also built — its section is still a placeholder below; that's a documentation gap to close, not a sign the subsystem is missing.)

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

_To be filled in as Milestone 4 lands._

## Memory architecture

_To be filled in as Milestone 5 lands._

## Conversation engine

_To be filled in as Milestone 6 lands._

## Embeddable widget

_To be filled in as Milestone 7 lands._

## Voice platform

_To be filled in as Milestone 8 lands._

## Security architecture

_To be filled in as Milestone 10 lands._

## Infrastructure & deployment

_To be filled in as Milestone 11 lands._

## Related documents

- [`docs/ROADMAP.md`](ROADMAP.md) — the 300-step implementation plan
- [`docs/adr/`](adr/) — Architecture Decision Records
- [`AGENTS.md`](../AGENTS.md) — the project's full engineering constitution
