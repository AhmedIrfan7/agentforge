# AgentForge Implementation Roadmap

300 steps, one commit each, pushed immediately after (see `AGENTS.md` §10 — Git Commit Discipline). Grouped into 14 milestones matching the GitHub Milestones this repo should carry. Do not batch steps into large commits; do not skip ahead without completing/testing the prior step.

**Stack locked in for this roadmap (see `docs/adr/0001-technology-stack.md`):**
Python + FastAPI (backend) · Next.js/React (dashboard) · vanilla TS (embeddable widget) · PostgreSQL + pgvector (data + vectors) · Redis + Celery (cache/queue/background jobs) · MinIO/S3 (object storage) · LangGraph (agent orchestration) · Docker Compose (local dev) · pnpm workspaces + uv (package management) · single monorepo.

Every provider-facing piece (LLM, embeddings, speech, vector store) sits behind an abstraction interface per `AGENTS.md` — swapping providers later must never require a rewrite.

---

## Milestone 0 — Foundation (steps 1–34)

- [x] 001. Init monorepo structure: `apps/`, `packages/`, `docs/`, `infra/`
- [x] 002. Add root `.gitignore`
- [x] 003. Add root `README.md` skeleton
- [x] 004. Add `LICENSE` (Apache 2.0)
- [x] 005. Add `CODE_OF_CONDUCT.md`
- [x] 006. Add `CONTRIBUTING.md` skeleton
- [x] 007. Scaffold `apps/api` FastAPI project (uv init)
- [x] 008. Add `pyproject.toml` with base deps (fastapi, uvicorn)
- [x] 009. Add ruff config for API — ruff only, not ruff+black (see step 009 commit; ruff format is black-compatible, running both was redundant)
- [x] 010. Add mypy config for API
- [x] 011. Add pytest config + first smoke test
- [x] 012. Scaffold `apps/web` Next.js project
- [x] 013. Add ESLint + Prettier config for web
- [x] 014. Add TypeScript strict config
- [x] 015. Add `pnpm-workspace.yaml`
- [x] 016. Scaffold `packages/shared` TS types package
- [x] 017. Add `docker-compose.yml` (Postgres+pgvector, Redis, MinIO) — config validated, not yet boot-tested (see 033)
- [x] 018. Add `.env.example` for api and web
- [x] 019. Add Makefile for common dev commands (`make` unavailable locally to test; commands verified directly)
- [x] 020. Configure pre-commit hooks (lint/format on commit)
- [x] 021. Add GitHub Actions workflow: lint
- [x] 022. Add GitHub Actions workflow: backend tests
- [x] 023. Add GitHub Actions workflow: frontend tests (build-check; no test suite exists yet)
- [x] 024. Add `GET /health` endpoint in API
- [x] 025. Add `docs/ARCHITECTURE.md` skeleton
- [x] 026. Add `docs/adr/` folder + ADR template
- [x] 027. Write ADR-0001: technology stack decision
- [x] 028. Write ADR-0002: monorepo vs multi-repo decision
- [x] 029. Write ADR-0003: multi-tenancy isolation strategy decision
- [x] 030. Add structured logging (structlog) in API
- [x] 031. Add centralized config module (pydantic-settings) in API
- [x] 032. Add Dockerfiles for api and web (multi-stage) — verified with real `docker build` + `docker run` for both apps (see step 033)
- [x] 033. Verify `docker compose up` boots api+web+db+redis+minio end-to-end — postgres+redis+minio all healthy via `docker compose up -d`, pgvector extension confirmed loadable; `apps/api` and `apps/web` Docker images built and run, both served real HTTP responses (`/health` → 200, web root → 200). Fixed a real bug found in the process: `apps/api/.python-version` was pinned to 3.14 (a local-machine workaround) which broke the container build against the `python:3.12-slim` base — repinned to 3.12.
- [x] 034. Add CI status badge to README

## Milestone 1 — Multi-Tenancy Core (steps 35–59)

- [x] 035. Add SQLAlchemy async engine setup
- [x] 036. Add Alembic migrations setup
- [x] 037. Create `Organization` model + migration
- [x] 038. Create `Workspace` model + migration — landed with 042+043, see their notes
- [x] 039. Create `User` model + migration — global identity, no auth fields yet (Milestone 2)
- [x] 040. Create `Membership` model (user↔org/workspace + role) + migration — tenant-scoped, RLS forced, two partial unique indexes for org-level vs workspace-level
- [x] 041. Create `Role`/`Permission` tables + migration — global catalog, 10 built-in roles seeded; Permission rows deliberately empty until Milestone 2 defines what they check
- [x] 042. Add `tenant_id` column + index convention to base model mixin — pulled forward before 038 (ADR-0003 requires tenant_id land in the same migration as the table, not bolted on after)
- [x] 043. Enable Postgres Row-Level Security policies on tenant tables — pulled forward with 042/038 for the same reason. **Found and fixed a real bug: the docker-compose bootstrap Postgres role is always a superuser and unconditionally bypasses RLS.** App runtime now uses a separate least-privilege `agentforge_app` role (see `infra/postgres/init/01-app-role.sql`, ADR-0003); migrations still use the bootstrap superuser. Verified with real cross-tenant read/write attempts against the actual least-privilege connection, not the superuser one.
- [x] 044. Add tenant-context dependency (`dependencies/tenant.py`) — the "resolve from JWT" half is an explicit `NotImplementedError` placeholder until Milestone 2's auth exists (deliberately not a client-header shortcut, see ADR-0003); the session/RLS-wiring half is real and tested end-to-end through FastAPI's dependency chain
- [x] 045. Add repository base class enforcing `tenant_id` filter on every query — `repositories/base.py`, `TenantScopedEntity` mixin added for clean generic typing
- [x] 046. Add test: cross-tenant query attempt is blocked — get/list/create all covered across `test_repository_base.py` and `test_tenant_isolation.py`
- [x] 047. Create Organization CRUD endpoints — fully functional, verified live against a running server (create/get/list/409/404/422/delete)
- [x] 048. Create Workspace CRUD endpoints — correctly wired but non-functional until Milestone 2 auth exists; verified both the fail-closed 500 and the working path via dependency override
- [x] 049. Add pagination utility for list endpoints — `schemas/common.py` (`Page[T]`, `PaginationParams`), `repositories/base.py:count()`
- [x] 050. Add API error-handling middleware (consistent schema, no internal leak) — `errors.py`
- [x] 051. Add Pydantic request/response schemas for org/workspace endpoints — `schemas/organization.py`, `schemas/workspace.py`
- [x] 052. Add integration tests for org/workspace endpoints — `test_organization_endpoints.py`, `test_workspace_endpoints.py`, 27/27 passing
- [x] 053. Add local dev seed script (demo org/workspace/user) — idempotent, verified live
- [x] 054. Add `AuditLog` table + model — `tenant_id` deliberately has no FK (outlives the org it's about)
- [x] 055. Add audit logging hook on org/workspace create/update/delete (no update endpoints exist yet, so create+delete only)
- [x] 056. Document tenant isolation approach in `docs/ARCHITECTURE.md`
- [x] 057. Add dedicated tenant-isolation pytest module — `test_tenant_isolation.py` (built alongside step 043)
- [x] 058. Add DB connection pooling config — `config.py`, applies outside tests only
- [x] 059. Add CI check: `alembic upgrade head` runs clean — plus `alembic check` for model/migration drift

## Milestone 2 — Authentication & Authorization (steps 60–81)

- [x] 060. Add password hashing utility (argon2)
- [x] 061. Create email/password signup endpoint
- [x] 062. Create login endpoint issuing JWT access+refresh tokens — found+fixed weak default JWT secret, added production startup guard against placeholder secrets
- [x] 063. Add refresh-token rotation endpoint — single-use rotation, replay of an old token correctly rejected
- [x] 064. Add logout/session revocation
- [x] 065. Add email verification flow — shared `VerificationToken` model (reused by 066, 067); found+fixed a real migration hazard against the seeded dev DB (NOT NULL column add needs server_default)
- [x] 066. Add magic-link login flow
- [x] 067. Add password reset flow — confirm revokes all other active sessions for the user, not just the password
- [x] 068. Add `Session` model (device/IP/last-active tracking) — built alongside step 061, since login needed it to issue refresh tokens against
- [x] 069. Add Redis-backed rate limiting on auth endpoints — per-IP fixed-window, disabled under test env (test suite legitimately exceeds real-world limits), verified live (3-request limit correctly 429'd on the 4th)
- [x] 070. Add RBAC permission-check FastAPI dependency — `dependencies/rbac.py:require_permission()`, union of permissions across every role the caller holds in the tenant
- [x] 071. Define role matrix (Super Admin, Org Owner, Admin, Manager, Knowledge Manager, Developer, Support Agent, Analyst, Viewer, End User, Guest) — seeded by migration `1d0ef14faf9e` (permission catalog + role→permission matrix)
- [x] 072. Enforce role checks per route via permission dependency — organization/workspace routes now require real JWT + membership + permission; found+fixed a real RLS bug (dependencies never set tenant context before querying Membership, so every check silently 403'd) and a real tenant-isolation leak (`list_organizations` returned all orgs unfiltered) along the way
- [x] 073. Add `Invitation` model + invite-teammate endpoint — `POST /organizations/{id}/invitations`, gated by new `invitation:create` permission (org_owner/admin/manager); opaque 7-day token (SHA-256 hashed, same pattern as VerificationToken); partial unique index blocks duplicate pending invites per (tenant, email)
- [x] 074. Add invitation-accept endpoint — `POST /invitations/accept`, token-only (no org in path); requires real auth + caller's email to match the invite; creates the Membership directly. Found and fixed a real production bug along the way: `tenant_isolation`'s RLS policy cast `''::uuid` on a reused pooled connection whose GUC had reverted from a prior request's `SET LOCAL` — invisible under pytest's NullPool, only surfaced live. Fixed with `NULLIF(..., '')` in `migrations/rls.py` and repaired every already-applied policy via migration `c5861fcf8c88`
- [x] 075. Add invitation expiration handling — `GET /organizations/{id}/invitations` (list, `invitation:read`) and `DELETE .../invitations/{id}` (revoke, `invitation:revoke`, idempotent, 409 if already accepted); `InvitationRead.status` derived from accepted_at/revoked_at/expires_at ("pending"/"accepted"/"revoked"/"expired") rather than stored; live-verified with real connection reuse, not just pytest
- [x] 076. Add Google OAuth login — `GET /auth/google/login`+`/callback`, server-side code exchange (no id_token re-verification needed), CSRF via double-submit state cookie, links-or-creates by Google-verified email, new `OAuthIdentity` table (not a `google_id` column, so step 077 doesn't need a schema change); found+fixed a real `Secure`-cookie-over-HTTP bug that would've broken every deployment not terminating TLS in the app process itself
- [x] 077. Add auth-provider abstraction interface (future SSO/SAML/OIDC) — `OAuthProvider` structural Protocol + `PROVIDERS` registry in `auth/oauth.py`; `routers/oauth.py` generalized to `/auth/{provider}/login`+`/callback` (Google's URLs unchanged); proved genuine via a test that registers an invented "github" provider and logs in through the same router with zero provider-specific branching
- [x] 078. Add MFA (TOTP) enrollment + verification — `POST /auth/mfa/enroll`+`/confirm`+`/disable` (real access token required) and `/verify` (redeems a short-lived `mfa_pending` JWT ticket for real tokens); TOTP secret encrypted at rest (Fernet), 10 argon2-hashed single-use backup codes; every primary-auth path (password/magic-link/Google OAuth) gated via a shared `complete_login()`, refresh exempt; found+fixed a real packaging bug (`httpx` only in dev deps, would've crashed a production Google-login the first time anyone tried it); live-verified with real TOTP codes end-to-end
- [x] 079. Add per-org `SecuritySettings` model (session timeout, password policy) — `GET`/`PATCH /organizations/{id}/security-settings` (org_owner+admin only), one row per org (auto-created + backfilled for existing orgs); `mfa_required` is the one field actually enforced (at `dependencies/tenant.py:get_current_tenant_id`, blocking every tenant-scoped route until the member enables MFA); session_timeout/password-policy fields are honest configuration-only for now — no clean enforcement point exists while User/Session stay global rather than org-scoped, documented directly rather than implied otherwise
- [x] 080. Add full auth-flow test (signup→verify→login→refresh→logout) — one continuous chain threading real data (signup's user id → its verification token → login's tokens → refresh rotation → logout revocation) through every step, catching integration gaps the existing per-endpoint tests' isolated fixtures can't; test-only, no new endpoints/models
- [x] 081. Add RBAC-enforcement tests (unauthorized role blocked) — systematic seeded role→permission matrix check (would catch a permission granted to the wrong roles, which every prior per-feature end_user-only test would miss) + real HTTP tests for previously-untested tier distinctions (admin vs org_owner-only delete, manager vs security_settings, viewer read-vs-write, guest's zero permissions). **Milestone 2 (Authentication & Authorization) complete — 81/300.**

## Milestone 3 — Knowledge Pipeline: Ingestion + RAG (steps 82–136)

- [x] 082. Create `KnowledgeBase` model + migration — sits under Workspace (org→workspace→knowledge base); deliberately minimal (no embedding/chunking config until steps 098-106 need it); also built minimal CRUD (create/list/get/delete, matching Workspace's own no-update scope) nested under `/organizations/{id}/workspaces/{id}/knowledge-bases`, since an inert model can't be reached/tested and step 084 needs a real target to upload into; `get_target_workspace` cross-checks the URL's workspace_id belongs to the resolved tenant (verified both cross-workspace and cross-org 404s)
- [x] 083. Create `Document` model + migration (status, metadata) — sits under `KnowledgeBase`; genuinely model-only (unlike 082) since step 084's file upload is what actually creates a Document, no throwaway create endpoint to build/discard; `status` plain str defaulting to "pending" (new pipeline stages are app-level additions, not migrations); `doc_metadata` JSONB (not `metadata` — reserved on every SQLAlchemy model); storage columns deliberately deferred to 084; tested at the ORM/RLS layer directly, no live-server check needed for a model-only step
- [x] 084. Add file upload endpoint (multipart → MinIO/S3) — `POST .../knowledge-bases/{id}/documents`; new `storage.py` (aioboto3, async S3-compatible client); Document gains `storage_key`/`content_type`/`size_bytes` (deferred from 083); deliberately no file-type/size validation (085/086) or virus scan (087) yet — real, tracked gaps, not hidden; live-verified with a real curl upload confirmed via `mc ls` in the bucket. CI needed a real MinIO service — `bitnami/minio:latest` turned out to not exist at all (confirmed via Docker Hub API, zero tags), fixed with a plain `docker run` step using the same `minio/minio:latest` image local dev uses, verified locally before repushing
- [x] 085. Add file-type allow-list validation (pdf, docx, pptx, xlsx, csv, txt, md, html, json, xml) — `validation.py`, two layers since neither extension nor client Content-Type is trustworthy: extension allow-list + magic-byte content check (`filetype`, pure Python) for pdf/docx/pptx/xlsx, UTF-8 decodability check for text formats (no binary signature exists for "this is text"); new `UnsupportedFileTypeError` (422, same `validation_error` code as pydantic validation); live-verified reject-bad-extension, reject-content-mismatch, and accept-real-signature all correct against a running server
- [x] 086. Add file-size limit validation — `config.max_upload_size_bytes` (50 MB default), enforced by `validation.py:read_upload_content` reading in bounded 1 MB chunks and bailing the moment the running total exceeds the limit, rather than buffering the whole upload first (which would defeat the point of a size limit); new `FileTooLargeError` (413, distinct from 422's validation_error); live-verified with `MAX_UPLOAD_SIZE_BYTES=10` against a running server, both reject and accept paths
- [ ] 087. Add virus/malware scan step (ClamAV) before processing
- [ ] 088. Add upload progress tracking (status field + polling)
- [ ] 089. Set up Celery worker app + Redis broker config
- [ ] 090. Add background task: content extraction dispatcher (per file type)
- [ ] 091. Add PDF text/structure extraction (headings, tables)
- [ ] 092. Add DOCX/PPTX/XLSX extraction
- [ ] 093. Add HTML/Markdown extraction
- [ ] 094. Add metadata-extraction step (title, author, dates, language)
- [ ] 095. Add Document Analysis Agent skeleton (classifies doc type)
- [ ] 096. Add document quality checks (empty pages, broken formatting, duplicate hash)
- [ ] 097. Add Chunking Recommendation Agent skeleton (scores strategies + explains choice)
- [ ] 098. Implement fixed-size chunker
- [ ] 099. Implement sentence/paragraph-aware chunker
- [ ] 100. Implement markdown/heading-aware chunker
- [ ] 101. Implement table-aware chunker
- [ ] 102. Implement recursive/hybrid chunker
- [ ] 103. Add chunking-strategy override endpoint (accept/override recommendation)
- [ ] 104. Persist chunking decision + reasoning on `Document`
- [ ] 105. Create `Chunk` model + migration
- [ ] 106. Add embedding-provider abstraction interface
- [ ] 107. Implement OpenAI embedding provider
- [ ] 108. Add background task: batched embedding generation
- [ ] 109. Add pgvector column + index on `Chunk`
- [ ] 110. Add background task: vector indexing
- [ ] 111. Add ingestion-pipeline status endpoint (per-stage visibility)
- [ ] 112. Add retry/backoff handling for failed pipeline stages
- [ ] 113. Add end-to-end ingestion test (fixture PDF → chunks+embeddings)
- [ ] 114. Add document re-index endpoint (on update/replace)
- [ ] 115. Add document versioning (replace preserves history)
- [ ] 116. Add tenant-scoped document deletion (cascades chunks+embeddings)
- [ ] 117. Add duplicate-document detection within a knowledge base
- [ ] 118. Add `VectorStore` abstraction interface
- [ ] 119. Implement pgvector `VectorStore` adapter
- [ ] 120. Add dense (vector similarity) retrieval endpoint
- [ ] 121. Add keyword/full-text retrieval (Postgres tsvector)
- [ ] 122. Add hybrid retrieval combining dense+keyword
- [ ] 123. Add metadata filtering in retrieval queries
- [ ] 124. Add Retriever Agent skeleton wrapping retrieval logic
- [ ] 125. Add reranking step (abstracted provider)
- [ ] 126. Add context-builder module (dedupe, order, token-budget aware)
- [ ] 127. Wire citation-tracking through retrieval→context→response
- [ ] 128. Add RAG evaluation harness (precision/recall on labeled fixtures)
- [ ] 129. Add retrieval-quality logging (query, results, scores, latency)
- [ ] 130. Add multi-query retrieval strategy
- [ ] 131. Add parent-child chunk retrieval strategy
- [ ] 132. Add tenant-isolation test for retrieval
- [ ] 133. Add knowledge-base search API endpoint
- [ ] 134. Add tenant-scoped retrieval caching (Redis)
- [ ] 135. Add benchmark dataset + regression-test script for retrieval
- [ ] 136. Document knowledge pipeline + RAG architecture in `docs/ARCHITECTURE.md`

## Milestone 4 — Agent System (steps 137–161)

- [ ] 137. Add LangGraph dependency + base agent-graph scaffold
- [ ] 138. Add `Agent` base class/interface (input/output schema, config)
- [ ] 139. Add Agent Registry (register/discover/health-check)
- [ ] 140. Add Orchestrator service skeleton
- [ ] 141. Add intent-analysis step in orchestrator
- [ ] 142. Add Planning Agent (selects agents + execution order)
- [ ] 143. Wire Retriever Agent into orchestrator graph
- [ ] 144. Add Memory Agent skeleton
- [ ] 145. Add Conversation Agent skeleton
- [ ] 146. Add Reasoning Agent skeleton
- [ ] 147. Add Quality Review Agent skeleton
- [ ] 148. Add Safety Agent skeleton (prompt-injection/unsafe-content checks)
- [ ] 149. Add Citation Agent (assembles citations into response)
- [ ] 150. Add LLM-provider abstraction interface
- [ ] 151. Implement OpenAI LLM provider
- [ ] 152. Implement Anthropic LLM provider
- [ ] 153. Add per-agent execution tracing (latency/tokens/status)
- [ ] 154. Add parallel execution for independent agent steps
- [ ] 155. Add agent failure handling (retry, fallback, partial-result degradation)
- [ ] 156. Add per-agent unit tests (mocked providers)
- [ ] 157. Add orchestrator integration test (full request→response trace)
- [ ] 158. Add per-assistant agent-configuration model
- [ ] 159. Create `Assistant` model + migration
- [ ] 160. Add Assistant CRUD endpoints
- [ ] 161. Document multi-agent architecture in `docs/ARCHITECTURE.md`

## Milestone 5 — Memory System (steps 162–175)

- [ ] 162. Create `Memory` model + migration (short-term/long-term/user/org/session)
- [ ] 163. Add Redis-backed short-term memory store (conversation-scoped)
- [ ] 164. Add Postgres-backed long-term memory store (importance-scored)
- [ ] 165. Add Memory Agent logic: decide what deserves long-term retention
- [ ] 166. Add identity-based memory retrieval on conversation start
- [ ] 167. Add memory-summarization background job
- [ ] 168. Add memory expiration/TTL policy engine
- [ ] 169. Add memory-privacy controls (view/export/delete own memory)
- [ ] 170. Add memory deletion endpoint (right-to-erasure)
- [ ] 171. Add tenant-isolation test for memory
- [ ] 172. Add memory-observability logging (created/updated/ignored + why)
- [ ] 173. Add memory conflict-resolution logic
- [ ] 174. Add memory-lifecycle tests (create→retrieve→expire→delete)
- [ ] 175. Document memory architecture in `docs/ARCHITECTURE.md`

## Milestone 6 — Conversation Engine (steps 176–200)

- [ ] 176. Create `Conversation` model + migration
- [ ] 177. Create `Message` model + migration
- [ ] 178. Add conversation-create endpoint
- [ ] 179. Add message-send endpoint wired through orchestrator
- [ ] 180. Add streaming response support (SSE)
- [ ] 181. Add conversation-state machine (new/active/waiting/processing/completed/archived)
- [ ] 182. Add paginated conversation-history endpoint
- [ ] 183. Add conversation search endpoint (keyword+semantic)
- [ ] 184. Add rename/pin/archive/delete conversation endpoints
- [ ] 185. Add markdown-rendering support in message schema
- [ ] 186. Add code-block/table formatting support
- [ ] 187. Add citation display in chat responses
- [ ] 188. Add regenerate-response endpoint
- [ ] 189. Add feedback endpoint (helpful/not helpful/incorrect/etc.)
- [ ] 190. Add follow-up-question suggestion generation
- [ ] 191. Add conversation-export endpoint (JSON/markdown)
- [ ] 192. Add anonymous-session support (pre-auth visitors)
- [ ] 193. Add user-identification-triggered memory reconnection
- [ ] 194. Build chat UI shell in `apps/web` (message list, input, streaming render)
- [ ] 195. Add typing-indicator UI
- [ ] 196. Add conversation-list sidebar UI
- [ ] 197. Add conversation-search UI
- [ ] 198. Add Playwright e2e test: send message → receive streamed response
- [ ] 199. Add per-tenant rate limiting on message-send
- [ ] 200. Document conversation lifecycle in `docs/ARCHITECTURE.md`

## Milestone 7 — Embeddable Widget (steps 201–215)

- [ ] 201. Scaffold `apps/widget` (vanilla TS, minimal deps)
- [ ] 202. Add widget build pipeline (single bundled JS output)
- [ ] 203. Add widget config loader (org/assistant ID from script tag)
- [ ] 204. Add widget launcher button UI
- [ ] 205. Add widget chat window UI (shares logic via `packages/shared`)
- [ ] 206. Add widget theming (colors/fonts/logo/position)
- [ ] 207. Add embed-code generator in dashboard
- [ ] 208. Add widget CORS/allowed-domains config per org
- [ ] 209. Add widget CDN deployment pipeline
- [ ] 210. Add widget versioning strategy (pinned script version)
- [ ] 211. Add widget dark/light mode support
- [ ] 212. Add widget mobile-responsive layout
- [ ] 213. Add widget bundle-size budget check in CI
- [ ] 214. Add widget smoke test (loads on fixture HTML page, sends message)
- [ ] 215. Document widget embedding process in docs

## Milestone 8 — Voice Platform (steps 216–232)

- [ ] 216. Add speech-provider abstraction interface (STT+TTS)
- [ ] 217. Implement Whisper STT provider
- [ ] 218. Implement TTS provider
- [ ] 219. Create `VoiceSession` model + migration
- [ ] 220. Add voice-session-start endpoint
- [ ] 221. Add streaming audio ingestion (websocket)
- [ ] 222. Add streaming TTS audio output
- [ ] 223. Add silence detection
- [ ] 224. Add voice-activity detection
- [ ] 225. Add barge-in/interruption handling
- [ ] 226. Wire Voice Agent into orchestrator (shares Conversation Agent intelligence)
- [ ] 227. Add voice-latency instrumentation
- [ ] 228. Add voice-session-end + transcript persistence
- [ ] 229. Add voice widget UI (mic button, waveform indicator)
- [ ] 230. Add voice tenant-isolation test
- [ ] 231. Add voice quality/latency benchmark script
- [ ] 232. Document voice architecture in `docs/ARCHITECTURE.md`

## Milestone 9 — Admin Dashboard & Analytics (steps 233–250)

- [ ] 233. Scaffold dashboard shell in `apps/web` (auth-gated layout, nav)
- [ ] 234. Add org-settings page (branding, security settings)
- [ ] 235. Add workspace-management UI
- [ ] 236. Add knowledge-base management UI (upload, list, status)
- [ ] 237. Add document detail view (chunking decision, quality warnings)
- [ ] 238. Add assistant-builder UI (instructions, knowledge access, agent config)
- [ ] 239. Add user/role-management UI
- [ ] 240. Add invitation-management UI
- [ ] 241. Add API-key management UI + endpoints
- [ ] 242. Add Analytics Agent skeleton (aggregates usage metrics)
- [ ] 243. Add conversation-analytics endpoint + dashboard chart
- [ ] 244. Add knowledge-health dashboard (duplicates, low-confidence, unused docs)
- [ ] 245. Add agent-performance dashboard
- [ ] 246. Add usage-tracking (messages/voice-minutes/uploads/storage per org)
- [ ] 247. Add audit-log viewer UI
- [ ] 248. Add system-health dashboard (queue depth, worker status, provider status)
- [ ] 249. Add platform-admin layer (cross-org super-admin views)
- [ ] 250. Add dashboard e2e test (login → upload doc → processed → chat → see analytics)

## Milestone 10 — Security & Observability (steps 251–266)

- [ ] 251. Harden Safety Agent: explicit separation of retrieved content from system instructions
- [ ] 252. Add strict schema validation on every API route (no raw dict passthrough)
- [ ] 253. Document secrets-management approach (env-based now, vault path documented)
- [ ] 254. Add encryption-at-rest for sensitive columns (API keys, tokens)
- [ ] 255. Add security-event audit logging (failed logins, permission denials, cross-tenant attempts)
- [ ] 256. Add OpenTelemetry tracing across API+workers
- [ ] 257. Add Prometheus-compatible metrics export
- [ ] 258. Add centralized error tracking (Sentry or equivalent)
- [ ] 259. Refine rate-limit + abuse-detection middleware
- [ ] 260. Add automated dependency-vulnerability scanning in CI
- [ ] 261. Add SAST scanning in CI
- [ ] 262. Add security test suite (auth bypass, cross-tenant, injection attempts)
- [ ] 263. Add incident-response runbook doc
- [ ] 264. Add `SECURITY.md` (responsible disclosure policy)
- [ ] 265. Add backup automation + restore-drill script
- [ ] 266. Document security architecture in `docs/ARCHITECTURE.md`

## Milestone 11 — Infrastructure & Deployment (steps 267–280)

- [ ] 267. Add production Dockerfiles (multi-stage, non-root user)
- [ ] 268. Add `docker-compose.prod.yml` reference deployment
- [ ] 269. Add self-hosted deployment documentation
- [ ] 270. Add CI/CD: build+push images on merge to main
- [ ] 271. Add staging-deployment workflow
- [ ] 272. Add production-deployment workflow with manual approval gate
- [ ] 273. Add health-check + readiness probes
- [ ] 274. Add horizontal-scaling config for API/workers
- [ ] 275. Add CDN config for widget assets
- [ ] 276. Add environment-config documentation (all env vars)
- [ ] 277. Add rollback-procedure documentation
- [ ] 278. Add infra-as-code skeleton (Terraform/Pulumi) for one reference cloud target
- [ ] 279. Add uptime/alerting integration
- [ ] 280. Document infra architecture in `docs/ARCHITECTURE.md`

## Milestone 12 — Open Source Readiness / Public Beta (steps 281–295)

- [ ] 281. Finalize README (quickstart, architecture diagram, screenshots)
- [ ] 282. Finalize `CONTRIBUTING.md` (dev setup, PR process, coding standards)
- [ ] 283. Add issue templates (bug/feature/research)
- [ ] 284. Add PR template
- [ ] 285. Set up GitHub labels
- [ ] 286. Set up GitHub milestones matching this roadmap
- [ ] 287. Add public-facing roadmap summary to README
- [ ] 288. Add `FAQ.md`
- [ ] 289. Document plugin/extension points
- [ ] 290. Add OpenAPI-generated API reference docs
- [ ] 291. Add demo knowledge base + assistant for new contributors
- [ ] 292. Add `CHANGELOG.md` + semantic-versioning setup
- [ ] 293. Tag `v0.1.0-beta` release
- [ ] 294. Publish public beta announcement (GitHub Discussions)
- [ ] 295. Collect and triage first round of community feedback

## Milestone 13 — v1.0 Release (steps 296–300)

- [ ] 296. Address beta feedback backlog
- [ ] 297. Run full security review pass
- [ ] 298. Run full performance benchmark pass
- [ ] 299. Final documentation review
- [ ] 300. Tag `v1.0.0` release

---

## Notes

- This roadmap is a living document. Update it as scope is refined — see `AGENTS.md` §13 "Roadmap Management."
- Each step above should become exactly one commit, pushed immediately after verification (`AGENTS.md` §10, §14).
- Steps deliberately end each subsystem with a "document in `docs/ARCHITECTURE.md`" step — do not skip these; future contributors rely on them.
- Provider-specific steps (OpenAI, Whisper, Google OAuth, etc.) are the *first* implementation behind an abstraction interface, not a permanent commitment — swapping/adding providers later is an additive step, not a rewrite.
