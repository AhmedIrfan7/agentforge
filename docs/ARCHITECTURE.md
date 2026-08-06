# AgentForge Architecture

This document describes the system **as implemented**, not as aspired to — it grows one section at a time as each subsystem lands, per the checkpoints built into `docs/ROADMAP.md`. For the full product/engineering vision this architecture serves, see [`AGENTS.md`](../AGENTS.md). For why specific technologies were chosen, see [`docs/adr/`](adr/).

## Status

Milestone 1 (Multi-Tenancy Core) in progress. Sections below are filled in as the corresponding roadmap milestone completes — an empty section means that subsystem doesn't exist yet, not that it was forgotten.

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

_To be filled in as Milestone 3 lands._

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
