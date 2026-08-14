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
- [x] 087. Add virus/malware scan step (ClamAV) before processing — `antivirus.py` speaks clamd's INSTREAM protocol directly over a raw `anyio` TCP socket (no client library — the only async one on PyPI, `aioclamd`, has had a single release since 2022); runs synchronously in the upload request itself since Celery doesn't exist until step 089, right after `validate_upload`/before `storage.upload_file`; new `InfectedFileError` (422, code `infected_file`, distinct from `validation_error` the same way `FileTooLargeError` got its own code); `docker-compose.yml`/CI gain a `clamav/clamav:1.5` service — the non-`_base` tag, chosen because it ships its virus database pre-loaded (no slow freshclam download on container start); caught a real mistake before it shipped: almost bind-mounted a host volume over `/var/lib/clamav`, which would've shadowed that pre-loaded database with an empty directory and forced the exact slow download the tag was chosen to avoid; live-verified against a real running server + real clamd — clean upload succeeds, the official EICAR test string is rejected with signature `Eicar-Test-Signature` (and got real-world confirmation the test bytes are genuine: Windows Defender quarantined the on-disk copy the moment it was written, had to pipe the content through curl's stdin instead)
- [x] 088. Add upload progress tracking (status field + polling) — `status` field itself already existed since step 083 with nothing new to add there (no processor exists yet to transition it); the real net-new piece is `GET .../documents/{id}/status`, a deliberately smaller sibling of the existing full `GET .../documents/{id}` (`DocumentStatusRead`: id/status/updated_at only) so a client polling for progress isn't re-fetching title/doc_metadata/content_type on every tick; reuses `document:read` (no new permission — same capability, smaller view); no model/migration changes, every future pipeline stage just sets `document.status` and it shows up here automatically; live-verified against a real running server (upload → poll → confirm smaller payload shape + 404 for unknown id)
- [x] 089. Set up Celery worker app + Redis broker config — `celery_app.py`, no real tasks yet (step 090 defines the first one); shares `config.redis_url` with the existing cache/rate-limiter connection rather than a second Redis; explicit `json` serializers, not Celery's pickle-capable default (RCE surface if the broker's ever compromised); dropped celery's own `[redis]` extra — its pinned redis version range conflicted with this project's already-declared `redis>=8.1.0` under uv, and was redundant anyway since redis is already a direct dependency; `ping` task exists only to prove the wiring, tested in-process via `Task.apply()` (no subprocess/broker in the automated suite — nothing dispatches a real task until 090, so a real round-trip belongs in live verification, not new CI flakiness for infra with no product surface yet); live-verified with a real worker process (`--pool=solo` needed on Windows dev, not Linux/CI) dispatching `ping.delay()` against real local Redis and getting `"pong"` back — bonus proof the worker survives a broker restart and reconnects on its own, discovered when Redis actually cycled mid-verification
- [x] 090. Add background task: content extraction dispatcher (per file type) — `extraction.py:dispatch_extraction`, the first real Celery task, dispatched from `upload_document` right after the Document row + audit log land; routes by extension through a plain `HANDLERS` dict (same shape as `auth/oauth.py:PROVIDERS`); only csv/txt/json/xml have a real handler (trivial UTF-8 decode genuinely IS the whole extraction for those — no structure to pull out the way there is from a PDF/DOCX); pdf/docx/pptx/xlsx/html/md land on the honest `"extraction_unsupported"` until 091-093 register theirs; new nullable `Document.extracted_text` (migration `b91be877b219`) for chunking (098+) to read later. **Three real bugs found live, not by inspection:** (1) worker never saw the task at all (`KeyError: 'dispatch_extraction'`) — a worker only knows tasks from modules it actually imported, `-A celery_app worker` alone doesn't import `extraction.py`; fixed with `celery_app.conf.imports` (not a direct import, which would be circular); (2) a second commit inside one task after `SET LOCAL app.current_tenant_id` had already lapsed silently filtered every row out of RLS's UPDATE policy → `StaleDataError` — the exact bug class step 074 found live, reproduced here for the identical reason; fixed by re-setting tenant context after the intermediate commit; (3) a second task in the same long-lived worker process crashed in asyncpg/proactor internals — `asyncio.run()` makes a new event loop per task, and a pooled connection bound to the first loop breaks when a later, different loop reuses it, the same "Event loop is closed" class `db.py` already avoids for pytest via `NullPool`; fixed with a new `db.py:get_worker_session` on its own `NullPool` engine for any process that creates a new loop per unit of work. Live-verified end-to-end with a real worker + real server: `.txt`/`.json` uploads poll through to `"extracted"` with correct `extracted_text`; `.pdf` lands on `"extraction_unsupported"` with `extracted_text` staying null.
- [x] 091. Add PDF text/structure extraction (headings, tables) — `extraction_pdf.py`, registered into `HANDLERS["pdf"]`; pdfplumber (MIT), not PyMuPDF/fitz (AGPL-3.0-or-commercial, a real license conflict with this Apache 2.0 project); font-size heuristic for headings (no PDF format has a native "this is a heading" concept) — two tiers (`#`/`##`) so a title and its section headings don't collapse together, verified against a real reportlab-generated PDF before trusting pdfplumber's actual word/table shape; detected tables become markdown pipe-tables, with table-bbox words excluded from line extraction and lines+tables interleaved back by vertical position so output reads in original page order without duplicating table contents as loose words; output is markdown deliberately — same convention step 093 (HTML/Markdown) and step 100 (markdown/heading-aware chunker) will share. Unit-tested against real generated PDFs (title→H1, heading2→H2, table→pipe-table no dup, reading order, empty-doc no crash) + one wiring test through the real dispatcher. Live-verified with a real worker + real server: uploaded a title+heading+table PDF, polled to `"extracted"`, confirmed `extracted_text` matched the source structure exactly.
- [x] 092. Add DOCX/PPTX/XLSX extraction — `extraction_docx.py`/`extraction_pptx.py`/`extraction_xlsx.py`, registered into `HANDLERS`; all three output markdown like pdf, same shared convention. python-docx: iterates the document body's raw XML children directly rather than the library's own flat `.paragraphs`/`.tables` lists — verified live those two lists silently drop the true relative order of a table sitting between two paragraphs; heading levels read straight from the paragraph's real style name ("Title"/"Heading N"), no heuristic needed since docx encodes them explicitly. python-pptx: a slide's title placeholder becomes a heading, other text frames become paragraphs, tables become markdown tables — verified live that a title-slide layout's title is `CENTER_TITLE`, not `TITLE`, so both are checked. openpyxl: `read_only`+`data_only`, each sheet becomes a heading plus one markdown table. `extraction_tables.py` promoted out of `extraction_pdf.py` once four extractors needed the identical rows-to-markdown logic — found and fixed a real bug in it along the way: `cell or ""` blanked out any cell whose real value was `0`/`False`/`""`, not just an actually-empty (`None`) cell, harmless for pdf's always-text cells but wrong for xlsx's typed ones; fixed to check `is None` specifically. Unit-tested against real docx/pptx/xlsx files built with each library's own writer (headings, tables, ordering, empty-doc no-crash) + three wiring tests through the real dispatcher. Live-verified with a real worker + real server: uploaded real docx/pptx/xlsx files (including a `0`/`False` xlsx cell) through the real HTTP endpoint, confirmed each `extracted_text` matched exactly what was authored.
- [x] 093. Add HTML/Markdown extraction — `extraction_html.py` registered into `HANDLERS["html"]`; markdownify (MIT), not html2text (GPL-3.0-or-later, a real license conflict with this Apache 2.0 project, same reasoning that ruled out PyMuPDF/fitz for pdf). Reconsidered markdown along the way: earlier docstrings assumed it would need its own structure-aware transformation like pdf/docx/pptx/xlsx; it doesn't, since markdown is already this pipeline's own target output format — an uploaded `.md` file's bytes already ARE the extracted content, same as csv/txt/json/xml, so `md` joined `HANDLERS` as a plain-text passthrough instead. Two things verified live before trusting them: markdownify's `strip=` option does not remove a tag's content, only its markdown formatting, so `<nav>`/`<footer>` text still leaked through — those plus `<header>`/`<aside>`/`<script>`/`<style>` are removed outright with BeautifulSoup's `.decompose()` first, an honest bounded cleanup based on unambiguous HTML5 semantics, not full "guess the article body" content extraction; and `table_infer_header` defaults to `False`, which breaks a table using plain `<td>` for its header row (a common real-world case) — set to `True`. Every extension `validation.py` allows now has a real handler; `"extraction_unsupported"` is defined but no longer reachable through any upload the API currently accepts. Live-verified with a real worker + real server: uploaded HTML with genuine nav/header/footer/aside/script/style noise plus a heading and a plain-`<td>` table, and a real markdown file — noise fully stripped, table converted correctly, markdown came back byte-for-byte unchanged.
- [x] 094. Add metadata-extraction step (title, author, dates, language) — `extraction_metadata.py:build_doc_metadata`, populates `Document.doc_metadata` in the same pass `dispatch_extraction` already runs (reuses the already-downloaded bytes/extracted text, no separate task). Per-format metadata lives next to each format's content-extraction function (docx/pptx `core_properties`, xlsx `workbook.properties` — its own `creator` field normalized to a common "author" key, pdf's own non-ISO-8601 date format parsed by hand, html `<title>`/`<meta name="author">`/`<html lang>`), returning raw uncleaned values; cleaning is centralized in `extraction_metadata.py` rather than duplicated five times. Two real sentinel-default gotchas found live before writing any cleaning logic: python-docx defaults an unset author to the literal string `"python-docx"`, openpyxl defaults an unset creator to `"openpyxl"` — neither a real name, both filtered; dates are deliberately NOT filtered the same way (both libraries default unset dates to their own fixed/dynamic values, not detectable via a sentinel), a known accepted limitation of trusting embedded document metadata. Language: an explicitly declared one (per-format field, or html's `lang` attribute) wins over statistical detection; falls back to py3langid (BSD) otherwise, using `norm_probs=True` — verified live that degenerate input (empty/garbage/single-char) converges to a low ~0.17 confidence versus ~1.0 for real text, making a confidence threshold meaningful rather than arbitrary; below it, language stays null rather than guessing wrong. Live-verified with a real worker + real server: docx with explicit title/author/created/language, pdf with explicit title/author (dates parsed from its real Info-dictionary timestamps), and a plain txt file for pure content-based language detection — all three came back with correct `doc_metadata`, including docx's undated `modified_at` correctly showing python-docx's own known 2013 default rather than a wrong value being silently hidden.
- [x] 095. Add Document Analysis Agent skeleton (classifies doc type) — `agents/document_analysis.py`, the first real agent (AGENTS.md SECTION 5); scoped to what the roadmap line actually asks (classification), not AGENTS.md's full aspirational responsibility list for this agent — table detection is already inherent to `extraction_tables.py` (091-093), duplicate-upload detection is its own later step (117). Classification is keyword-phrase scoring into faq/manual/legal/academic/business (falls back to `"general"`), not an ML model or LLM call — same "don't overclaim precision" stance as the PDF heading heuristic and the language-confidence threshold; the winning category's matched keywords are reported alongside the classification, explainable by construction rather than a fabricated confidence score. No shared `Agent` base class/registry yet despite AGENTS.md describing a full Agent Registry/Orchestrator architecture — mirrors how OAuth was built here (concrete Google implementation first, step 076; generalized into a real Protocol + registry only once a second provider existed to prove the abstraction was real, step 077) — extracting a shared shape from one agent would be designing against a guess; revisit once 097 (Chunking Recommendation Agent) lands. Wired into `extraction.py:_run_extraction` right after metadata extraction, same pass, reusing the already-in-memory `extracted_text`; result lands in `Document.doc_metadata` as `document_type`/`document_type_signals`. Live-verified with a real worker + real server: uploaded a real FAQ-formatted document, confirmed `doc_metadata` came back with `document_type: "faq"` and the matched signal.
- [x] 096. Add document quality checks (empty pages, broken formatting, duplicate hash) — `quality.py`, computed in the same extraction pass as steps 094/095, informational only (not upload-blocking — that's `validation.py`'s job at upload time). `content_hash` = SHA-256 of raw bytes, its own indexed `Document` column (not JSONB) so step 117 (duplicate-document detection) can query it efficiently later — this step only computes/stores the signal, doesn't act on it. `is_empty`/`has_broken_formatting` land in `doc_metadata`; `is_empty` is whole-document not literally per-page (no extractor currently returns a per-page breakdown, only one combined string — honest about that rather than claiming page-level detection); `has_broken_formatting` flags >5% Unicode replacement/control characters, threshold verified live against clean vs. deliberately corrupted text. Live-verified with a real worker + real server: two files with identical content under different names produced identical `content_hash` (plus a SHA-256("") sanity check on an empty upload), and a genuinely empty file correctly flagged `is_empty: true`.
- [x] 097. Add Chunking Recommendation Agent skeleton (scores strategies + explains choice) — `agents/chunking_recommendation.py`, the second real agent; scores five candidates (fixed_size, sentence_paragraph, markdown_heading, table_aware, recursive_hybrid) from real structural signals in the extracted markdown (heading/table lines, paragraph breaks, length) — heuristic, not ML/LLM, same stance as the PDF heading heuristic. All five get scored, not just the winner (AGENTS.md's own "compare them, score them" framing). None of the five have a real chunker yet (098-102) — the recommendation itself is this step's deliverable, for step 103's override endpoint. Extracted `agents/base.py`'s minimal `Agent` (just `name`, no shared `run()`) now that a second real agent exists to compare against 095's — the two share an input type but do genuinely different things through differently-named methods (`analyze` vs `recommend`), so `name` (for independent logging) is the only honest shared contract. Real bug caught by testing: `recursive_hybrid`'s first scoring version could only ever tie a single-strategy score at the 1.0 ceiling, never beat it, so a genuinely mixed document (strong tables AND headings) lost the tie to `table_aware` instead of recommending the hybrid strategy built for that exact case — fixed by deriving `recursive_hybrid`'s score from the already-computed table/heading scores and switching the winner selection to `>=` with `recursive_hybrid` listed last, so it wins precisely the tie against the strategies it exists to combine. Wired into `extraction.py:_run_extraction`, same pass as 094-096. Live-verified with a real worker + real server: uploaded a real table-heavy document, confirmed the stored recommendation correctly picked `table_aware` with all five scores and matching reasoning.
- [x] 098. Implement fixed-size chunker — `chunking_fixed_size.py`, first of the five strategies `agents/chunking_recommendation.py` (097) scores among; pure algorithm only, nothing wired in yet (`Chunk` isn't a DB model until step 105, no real dispatch until 099-102 and 104 also land). Character-based, not token-based — no tokenizer/embedding provider exists yet (107) to tie a token budget to. 1000-char chunks by default, snapped back to the nearest whitespace so a chunk doesn't end mid-word (basic hygiene, not 099's sentence/paragraph awareness), falls back to a hard cut only when no whitespace exists within the lookback window — verified live in a REPL against a pathological 5000-char single "word" that it degrades gracefully rather than hanging. 200-char overlap between consecutive chunks, standard RAG practice. No server/API touches this yet, so unit tests (empty/short/multi-chunk/overlap/coverage/indices/word-boundary/pathological-word/reconstruction, 9 cases) are the real verification, not a live curl check.
- [x] 099. Implement sentence/paragraph-aware chunker — `chunking_sentence_paragraph.py`, second of five strategies `agents/chunking_recommendation.py` scores among; pure algorithm, nothing persisted yet (`Chunk` isn't a DB model until step 105). Packs whole paragraphs together when they fit, falls back to whole sentences for an oversized paragraph, and only an individual oversized sentence falls all the way back to `chunk_fixed_size`'s raw character splitting — composing the two chunkers instead of duplicating word-safe splitting logic. `Chunk` itself promoted out of `chunking_fixed_size.py` into a new `chunking_types.py` now that a second chunker needs the identical shape, same "build inline for the first consumer, promote once a second needs it" pattern `extraction_tables.py` already used. Sentence splitting is a real, bounded regex heuristic, not NLP — verified live first; known, accepted limitation on abbreviations ("Dr. Smith" splits after "Dr."), which doesn't meaningfully hurt chunk quality since the stray fragment gets packed back in with its neighbors. Real bug caught by testing, not inspection: paragraph offset tracking via `text.find("\n\n", ...)` silently dropped an extra newline when a document had more than one blank line between paragraphs, corrupting every later offset — fixed by switching to a regex scan over runs of blank-line whitespace.
- [x] 100. Implement markdown/heading-aware chunker — `chunking_markdown_heading.py`, third of five strategies `agents/chunking_recommendation.py` scores among; same pure-algorithm scope as 098/099. Splits along `#` through `######` heading boundaries (matching every extractor's own output shape), packs small adjacent sections together, and an oversized section falls back to `chunk_sentence_paragraph` for its own content — composing rather than re-implementing a third packing pass. Known, accepted limitation: when an oversized section sub-splits, only its first resulting piece carries the heading text — `Chunk.text` staying an exact substring of the source (same invariant 098/099 hold) mattered more than repeating the heading into every fragment. Promoted the packing algorithm itself into a new `chunking_packing.py` once it turned out byte-for-byte identical to `chunking_sentence_paragraph.py`'s own — same "build inline for the first consumer, promote once a second needs it" pattern already used for `Chunk` and `rows_to_markdown`; both chunkers now share one implementation.
- [x] 101. Implement table-aware chunker — `chunking_table_aware.py`, fourth of five strategies `agents/chunking_recommendation.py` scores among; same pure-algorithm scope as 098-100. Splits text into alternating table/prose regions (contiguous `| ... |` line runs vs everything else); prose regions get `chunking_sentence_paragraph.py`'s own paragraph/sentence splitting, composed not reimplemented. Tables become one atomic unit each, no matter how large — deliberately never split a table across a chunk boundary, since a mid-row cut destroys its meaning far more than an oversized chunk costs; verified live that a table well over `chunk_size` still comes back as exactly one whole chunk. First chunker in this pipeline where atomicity deliberately wins over the size cap for a specific unit type. Reuses `chunking_packing.py:pack_units`, same shared implementation the two chunkers before it use. One unrelated test (`test_organization_create_and_delete_are_audited`) flaked on the first full-suite run, passed clean on an isolated re-run and a full re-run — confirmed transient, not a regression, before treating the suite as green.
- [x] 102. Implement recursive/hybrid chunker — `chunking_recursive_hybrid.py`, fifth and last strategy `agents/chunking_recommendation.py` scores among; same pure-algorithm scope as 098-101. Genuinely hybrid, not just another single technique: splits by heading section first, then only within oversized sections protects tables as atomic units and packs surrounding prose by paragraph/sentence — combining what the markdown-heading chunker (respects sections, doesn't protect tables) and table-aware chunker (protects tables, no heading concept) each handle alone but not together. Matches exactly what the recommendation agent scores this strategy for: documents with both strong table and strong heading signals at once. Verified live against a table sitting inside an oversized section — came back completely whole. Promoted `split_sections`/`split_table_and_prose_regions` out of the markdown-heading and table-aware chunkers into a new shared `chunking_regions.py` since this one needed both — same "build inline for the first consumer, promote once a second needs it" pattern used throughout this pipeline. All five chunking strategies now exist as pure, fully-tested algorithms.
- [x] 103. Add chunking-strategy override endpoint (accept/override recommendation) — `PATCH .../documents/{id}/chunking-strategy`. One endpoint covers both actions: the caller always states the strategy they want, compared against the agent's own recommendation (if any) to decide the stored `source` ("accepted"/"override") — no need for two separate actions on one resource. New `document:update` permission (org_owner/admin/manager, same tier as `document:create/read`) — first document-mutation permission beyond create. `agents/chunking_recommendation.py`'s strategy tuple made public (`STRATEGY_NAMES`) so the router validates against the same source of truth, not a duplicated list; unknown name → 422 listing real allowed values. Only records the decision in `doc_metadata` for now — step 104 promotes to real `Document` columns, nothing dispatches real chunking against it yet (step 105 creates `Chunk` first). Live-verified against a real running server: no-recommendation override, accepting a real recommendation, overriding one (reasoning correctly names the original recommended strategy, not the previous decision), rejecting an unknown name, 404 for a nonexistent document, and confirmed each successful call wrote its own audit log entry.
- [x] 104. Persist chunking decision + reasoning on `Document` — `chunking_strategy`/`chunking_strategy_source`/`chunking_strategy_reasoning` real columns, promoted out of step 103's `doc_metadata["chunking_decision"]`. `doc_metadata["chunking_recommendation"]` stays JSONB (genuinely multi-field diagnostic scores); the single chosen strategy gets real columns instead. `extraction.py` now sets a real default the moment a recommendation exists (`source="recommended"`); the override endpoint updates the same columns to `"accepted"`/`"override"`. Three states, not two — "unreviewed" is meaningfully different from "human-confirmed," useful for an eventual admin queue. Comparison for accept/override still reads the ORIGINAL recommendation from `doc_metadata`, not the current column (which changes as overrides happen) — verified live that overriding twice in a row still correctly names the true original recommendation both times. Surfaced all three on `DocumentRead` (unlike `extracted_text`/`content_hash`, deliberately not exposed) since there's no dedicated GET for just the decision. Live-verified end to end with a real worker + server: real extraction set the recommended default, accept, then double-override, all correct.
- [x] 105. Create `Chunk` model + migration — mirrors `chunking_types.py:Chunk`'s shape (`text`/`start`/`end`/`index`) plus tenant-scoping and `document_id` FK (CASCADE). RLS enabled and verified directly against Postgres (`relrowsecurity = t`), not just assumed from calling `enable_rls()`. `(document_id, index)` unique. No embedding columns yet (106-109's job), no repository either — genuinely model-only, same precedent Document itself set at step 083, tested directly at the ORM/RLS layer (create/read, ordering, unique-constraint rejection, cascade-delete). Real, honest gap documented in the model's own docstring: nothing dispatches chunking yet — no code path creates a `Chunk` row from a document's `extracted_text` + `chunking_strategy`; the roadmap has no step between this one and 108 ("batched embedding generation") dedicated to that dispatch. Real bug caught before shipping: the first `alembic revision --autogenerate` came back completely empty — `Chunk` wasn't registered in `models/__init__.py`, which `migrations/env.py` relies on (`import models`, not per-file discovery) for autogenerate to see any model at all. Deleted the empty stub, fixed the registration, regenerated for real.
- [x] 106. Add embedding-provider abstraction interface — `embeddings/base.py:EmbeddingProvider`, a structural Protocol matching `auth/oauth.py:OAuthProvider`'s own precedent (self-contained adapter per provider, no shared inheritance). Deliberately sequenced interface-first, unlike OAuthProvider which stayed concrete through one implementation before generalizing — this roadmap puts the abstraction (106) before any real provider (107), so there's no earlier single-implementation step to generalize away from, and no `PROVIDERS` registry yet either, matching this project's "don't build machinery before there's something real to put in it" discipline. `embed()` is batch-shaped (`list[str] -> list[list[float]]`) from the start since step 108's own name ("batched embedding generation") already commits to batching being how the pipeline calls a provider. `dimensions` is a real required property, not speculative — step 109's pgvector column needs a fixed vector size at table-creation time. No error-handling contract specified beyond "async, can raise" — left for step 107's real OpenAI adapter to define from an actual failure mode, not guessed at here. Tested with a real dataclass implementation (`_FakeEmbeddingProvider`), not a mock, proving the Protocol shape actually works the way it promises. Unrelated to this step: diagnosed and fixed a local-only test-DB hygiene issue — `test_chunk_model.py` uses fixed slugs and real commits with no rollback/truncate fixture, so re-running the file in isolation and then the full suite back-to-back (both against the same local Postgres container) collided on leftover rows from the first run; confirmed via CI's workflow file that this can't happen there (fresh service-container Postgres per run) — not a code regression, just local dev-DB state, cleaned up with a targeted `DELETE ... WHERE slug LIKE 'chunk-%'`.
- [x] 107. Implement OpenAI embedding provider — `embeddings/openai.py:OpenAIEmbeddingProvider`, the first real `EmbeddingProvider`. Speaks OpenAI's REST `/v1/embeddings` endpoint directly over `httpx`, same "direct authenticated server-to-server call, no vendor SDK needed for one endpoint" reasoning `auth/oauth.py:GoogleOAuthProvider` already established. Verified the real request/response JSON shape (headers, `model`/`input`/`dimensions` fields, `data[].index`/`embedding`, `usage`) against OpenAI's own API docs before writing any code against it. `text-embedding-3-small` chosen as the model — cheapest current OpenAI embedding model, 1536 native dimensions, matched exactly by `dimensions = 1536` on the class (no truncation `dimensions` param sent, since 1536 already is this model's native size). Deliberately no `PROVIDERS` registry, unlike OAuth's own step 077 — that registry only earned its keep once a SECOND real provider existed to prove the abstraction was real; nothing later in this roadmap ever adds a second embedding provider (150-152/216-218 are the LLM/speech interfaces, not this one), so a registry here would be permanent machinery with nothing to ever hold. Response rows sorted by `index` defensively rather than trusting list order. New `EmbeddingProviderError` (plain `Exception`, not `errors.py`'s `AppError`) is the one thing any failure mode (auth, rate limit, network, malformed response) translates to — deliberately not an `AppError` since this runs inside a Celery task, not a FastAPI request/response cycle, so there's no HTTP status code to carry. **Honest, documented gap**: no real `OPENAI_API_KEY` is configured in this environment, so real live verification against OpenAI's actual API wasn't possible — request/response/error logic is instead verified with `httpx.MockTransport` (built into httpx, no new dependency), which exercises the provider's real code path end to end against a realistic (if fake) response, same spirit as `SecuritySettings`' own honestly-unenforced-fields precedent (step 079) rather than silently skipping or falsely claiming live verification. Whoever adds a real key later should do one real live call to close this gap for good.
- [x] 108. Add background task: batched embedding generation — `embeddings_pipeline.py:dispatch_embedding_generation`, dispatched automatically from `extraction.py:dispatch_extraction` right after a successful extraction (same "one stage's success kicks off the next" shape `upload_document` already uses). Genuinely folds in two other steps' literal scope, both by real necessity, both explicitly documented here and in the code: (1) **closes step 105's long-documented gap** — nothing dispatched chunk creation before this; `CHUNKERS` maps `agents/chunking_recommendation.py:STRATEGY_NAMES` to the five real chunker functions (098-102), same plain-dict-registry shape as `auth/oauth.py:PROVIDERS`/`extraction.py:HANDLERS`; (2) **folds in step 109's own literal task** (`Chunk.embedding`, pgvector `Vector(1536)` + ivfflat cosine-ops index) ahead of its number, since computing a real, paid embedding with nowhere durable to store it would mean discarding a real OpenAI response or inventing a throwaway column just to redo it a step later — both worse than building the already-fully-specified (by 106/107) schema now. `CREATE EXTENSION vector` added manually to the migration (nothing in this repo had installed the extension before now, despite Milestone 0 confirming it was merely *loadable*). Texts batched in groups of 100 per `EmbeddingProvider.embed()` call — large enough to be efficient, small enough that one failed batch (112's future job to retry) doesn't waste an entire large document's already-computed embeddings. **Known, accepted, explicitly-documented tension, not silently resolved**: this fires immediately with no window for step 103's override endpoint to act first; re-chunking after an override isn't built (`models/chunk.py` already flagged this as a future concern), so overriding after this task runs keeps the old chunks/embeddings. Live-verified end to end against a real server + real worker + real Postgres: upload → real extraction → automatic dispatch → correctly failed closed with `document.status="embedding_failed"` and **zero orphaned `Chunk` rows** (no real `OPENAI_API_KEY` configured in this environment — the `httpx.LocalProtocolError: Illegal header value b'Bearer '` failure is the expected, correctly-handled shape of that gap, not a bug). The success path (chunk creation, batching, vector storage, status→`"embedded"`) is verified for real against Postgres — real inserts through the least-privilege `agentforge_app` role, not the migrations superuser — with a fake `EmbeddingProvider` swapped in via `tests/test_embeddings_pipeline.py`, same reasoning `test_google_oauth_endpoints.py:FakeOAuthProvider` already established for swapping a whole provider rather than mocking calls inside a real one.
- [x] 109. Add pgvector column + index on `Chunk` — completed as a necessary, explicitly-documented part of step 108's own scope (see that entry) rather than redone here: `Chunk.embedding` is `pgvector.sqlalchemy.Vector(1536)`, nullable, plus `ix_chunks_embedding_ivfflat` (`ivfflat`, `vector_cosine_ops`, `lists=100`) — chosen over `hnsw` as this project's default first ANN index (cheaper to build, good enough at the row counts a real deployment starts at); tuning/rebuilding it as data grows is explicitly left to step 110's own background task, not this migration's job to get right forever. Verified directly against real Postgres, not just assumed from the migration succeeding: `\d chunks` confirms the column type and index, `\dx` confirms the `vector` extension is actually installed, and `alembic check` reports zero drift.
- [x] 110. Add background task: vector indexing — `vector_maintenance.py:reindex_chunk_embeddings`, `REINDEX INDEX CONCURRENTLY` on `ix_chunks_embedding_ivfflat`. A genuinely distinct concern from 108's embedding generation, matching AGENTS.md's own "DOCUMENT PIPELINE OBSERVABILITY" list, which names "Embedding generation" and "Vector indexing" as separate stages: 108 computes and stores one vector per chunk; this task keeps the ANN index itself healthy as those vectors accumulate. Verified against pgvector's own documented guidance before building this: ivfflat centroids are computed once, at build/reindex time, from whatever data exists in the table right then — an index built (or last reindexed) against an empty or unrepresentative sample keeps degraded recall *permanently*, not temporarily, until rebuilt against real data. `ix_chunks_embedding_ivfflat` was created by 108/109's migration against an empty `chunks` table, so it starts in exactly that degraded state by pgvector's own stated failure mode, not a hypothetical future concern. `REINDEX CONCURRENTLY` specifically (not a plain `REINDEX`, which exclusive-locks the table for its duration) — cannot run inside a transaction block, so this uses AUTOCOMMIT isolation on a dedicated connection, verified live before trusting it. **Real, load-bearing finding, live-verified, not assumed:** running this as the app's normal least-privilege `agentforge_app` role fails — `ERROR: must be owner of index` — REINDEX requires index ownership on Postgres 16 (the `MAINTAIN` privilege that would let a non-owner role do this doesn't exist until Postgres 17). Fixed by routing this one task through `settings.database_migrations_url` (the bootstrap/superuser connection Alembic already uses) instead — `config.py`'s docstring updated to document this as a narrow, honest, deliberate second use, not a silent boundary violation: REINDEX touches no tenant data, so it isn't a meaningful security regression against this project's least-privilege stance. No scheduler dispatches this automatically — the roadmap never adds Celery Beat or any periodic-task infrastructure, so "background task" here means a real, dispatchable Celery task like every other one in this codebase; who/what triggers it (pgvector's own guidance: monthly/quarterly, or after a large ingestion burst) is real operator/ops work this roadmap doesn't ask for yet. Tested against real Postgres, not mocked — a mocked connection would hide exactly the permission failure this step actually found.
- [x] 111. Add ingestion-pipeline status endpoint (per-stage visibility) — `GET .../documents/{id}/pipeline-status`, richer than step 088's single-string `/status`: a per-stage breakdown (`pipeline_status.py:compute_pipeline_stages` — extraction/chunk_generation/embedding_generation) plus real `Chunk` counts (`repositories/chunk.py`). Deliberately doesn't claim all eight of AGENTS.md's named pipeline stages: upload/validation both happen synchronously before a `Document` row even exists, `vector_indexing` (step 110) is a property of the shared ivfflat index across every chunk, not per-document state, and "publication" has no real concept anywhere in this codebase yet (no draft/published distinction exists) — reporting fake state for any of those would be worse than the honest three-stage view this ships instead. `chunk_generation` in particular is grounded in a real, queried `Chunk` count, not inferred from `Document.status` alone, since `extraction.py` and `embeddings_pipeline.py` can be mid-transition between each other. Live-verified end to end against a real server + worker: a document that fails at the embedding stage (same no-`OPENAI_API_KEY` gap steps 107/108 already documented) correctly shows `extraction: completed`, `chunk_generation: failed`, `embedding_generation: failed`, `chunk_count: 0` — matches the real all-or-nothing per-document commit behavior 108 already proved.
- [x] 112. Add retry/backoff handling for failed pipeline stages — `dispatch_extraction`, `dispatch_embedding_generation`, and `reindex_chunk_embeddings` (110) all now retry with exponential backoff (`autoretry_for`/`retry_backoff`) up to their existing `max_retries=5` ceiling. **Real, load-bearing gap found and fixed, not assumed:** `max_retries=5` had been set on `dispatch_extraction`/`dispatch_embedding_generation` since their own introduction (090/108), but nothing ever actually called `self.retry()` or configured `autoretry_for` for a genuine pipeline failure — only `dispatch_extraction`'s narrow `_DocumentNotFoundYet` race (a flat 1s retry, unrelated to real failures) ever retried anything. A real extraction or embedding failure previously got exactly one attempt, no retry, despite `max_retries` implying otherwise. Confirmed via `celery/app/autoretry.py`'s own source that `self.retry()`'s `Retry` exception passes through `autoretry_for`'s wrapper untouched (`except Retry: raise`), so the existing manual `_DocumentNotFoundYet` handling and the new blanket `autoretry_for=(Exception,)` compose safely without double-counting. **Known, accepted, explicitly documented limitation:** this doesn't distinguish a transient failure (worth retrying) from a permanent one (a file that will never parse, an invalid API key) — both burn the full retry budget before landing on their terminal failed status; a real retryable-vs-permanent classification is real future work, not built here. Verified two ways: `Task.apply()` eager-mode tests proving actual retry-then-succeed and retry-then-give-up behavior (confirmed live first that eager retries don't sleep in wall-clock time, so this stayed fast — 4 tests, under 2 seconds), and a real worker against real Redis, watching `dispatch_embedding_generation` genuinely retry with real backoff delays (1s, 0s, 2s, 7s, 2s observed) through 5 attempts before failing closed on the same no-`OPENAI_API_KEY` gap 107/108/111 already documented.
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
