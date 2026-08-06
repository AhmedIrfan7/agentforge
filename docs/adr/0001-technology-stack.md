# ADR-0001: Core Technology Stack

## Status
Accepted — 2026-08-06

## Problem
AgentForge needs a stack that can carry an AI-heavy multi-agent RAG backend, a multi-tenant SaaS dashboard, and a lightweight embeddable widget, while staying simple enough for solo development today and credible for enterprise deployment later (`AGENTS.md` §1, §4).

## Decisions

### Backend: Python + FastAPI
**Alternatives considered:** Node.js + TypeScript (single language across the stack).
**Why FastAPI:** The AI/agent ecosystem (LangGraph, LangChain, most embedding/vector/eval tooling) is Python-first. Building the multi-agent orchestrator, RAG pipeline, and document-analysis agents in Python avoids fighting the ecosystem or maintaining parallel Python microservices next to a Node core. FastAPI gives async I/O, Pydantic validation, and OpenAPI generation for free.
**Tradeoff accepted:** Two languages in the repo (Python backend, TypeScript frontend) instead of one. Mitigated by `packages/shared` for cross-language type contracts (OpenAPI-generated client types).

### Repository layout: single monorepo
**Alternatives considered:** Multi-repo (one repo per service) from day one.
**Why monorepo:** Solo development today; a monorepo (`apps/api`, `apps/web`, `apps/widget`, `packages/shared`) keeps atomic cross-cutting changes (e.g., an API schema change and its frontend consumer) in one commit and one PR. Matches `AGENTS.md` §4 guidance to avoid unnecessary microservices complexity before it's earned. Nothing here prevents extracting services into separate repos later if/when a team grows into it.
**Tradeoff accepted:** Will need CI path-filtering as the repo grows so unrelated changes don't trigger full-stack builds.

### Vector store: pgvector on PostgreSQL
**Alternatives considered:** Qdrant (self-hosted, purpose-built vector engine) from day one; Pinecone (managed).
**Why pgvector:** One database to operate, back up, secure, and reason about instead of two, while the platform has one tenant (us). Wrapped behind the `VectorStore` interface (roadmap step 118) so migrating to Qdrant/Pinecone later — when retrieval volume or latency actually demands it — is a new adapter, not an architecture change. Matches `AGENTS.md` §4 "avoid vendor lock-in" and §12 "avoid premature optimization."
**Tradeoff accepted:** pgvector's ANN performance falls behind dedicated vector engines at very large scale. Acceptable now; the abstraction is the escape hatch, not a permanent bet.

### Local development: Docker Compose
**Alternatives considered:** Cloud-hosted dev services from day one.
**Why Docker Compose:** Postgres, Redis, and MinIO run locally with one command and no cost, matching the "clone, configure env, start services" onboarding bar `AGENTS.md` §12 sets for contributors.

### Supporting choices made alongside the above
- **Frontend:** Next.js/React for the dashboard — consistent with the rest of the author's toolset and React's component ecosystem for a complex, stateful admin UI.
- **Embeddable widget:** separate `apps/widget`, vanilla TypeScript, no framework — must stay small and load fast on arbitrary third-party sites (`AGENTS.md` §7 "CDN Embed Architecture").
- **Agent orchestration:** LangGraph — graph-based multi-agent orchestration with built-in state handling, fits the Planner→Agents→Aggregator shape `AGENTS.md` §5 describes.
- **Background jobs:** Celery + Redis — mature, well-understood Python task queue for document ingestion, embedding generation, and memory summarization.
- **Object storage:** MinIO locally (S3-compatible), swappable to real S3/equivalent in production without code changes.
- **Package management:** `uv` for Python, `pnpm` workspaces for TypeScript — both fast, both increasingly the default choice in their ecosystems.

## Consequences
- Every provider-facing subsystem (LLM, embeddings, speech, vector store) must be built behind an interface from its first commit — this is a hard rule for all future roadmap steps in these areas, not just an ideal.
- Two toolchains (Python + Node) means two sets of linting/testing/CI jobs (`docs/ROADMAP.md` steps 009–011, 013–014, 021–023) — accepted as the cost of using the right tool for each layer.
- Future migration paths are documented, not deferred indefinitely: if organization count or retrieval volume outgrows pgvector, or if the monorepo outgrows solo/small-team development, those are new ADRs, not surprises.

## Future migration path
- Vector store: pgvector → Qdrant/Pinecone via new `VectorStore` adapter, triggered by measured retrieval latency/scale, not speculation.
- Repo layout: monorepo → split repos per service, triggered by team growth or independent release-cadence needs.
