# ADR-0003: Multi-Tenancy Isolation Strategy

## Status
Accepted — 2026-08-06

## Problem
`AGENTS.md` §7 and §9 treat tenant isolation as non-negotiable: one organization must never be able to see or affect another's data, at every layer, with no exceptions. This has to be decided before Milestone 1 (Multi-Tenancy Core) writes a single model, because retrofitting isolation onto an already-built schema is exactly the kind of rewrite the constitution says to avoid.

## Decisions

### Isolation model: shared database, `tenant_id` column, Postgres Row-Level Security, enforced again at the application layer
**Alternatives considered:**
- **Database-per-tenant:** one physical Postgres database per organization.
- **Schema-per-tenant:** one Postgres schema per organization, shared database/instance.
- **Shared tables + `tenant_id` column, application-enforced only** (no RLS).

**Why shared DB + `tenant_id` + RLS + app-layer enforcement:**
- *vs. database-per-tenant:* trivially strong isolation, but operationally unworkable at the scale `AGENTS.md` §7 targets (1 → 10,000+ organizations) — migrations, connection pooling, and backups would all need to run per-tenant. This is the kind of premature-for-current-scale complexity ADR-0001 already rejected for infrastructure generally.
- *vs. schema-per-tenant:* better isolation than a shared table, but Postgres doesn't scale well past low thousands of schemas in one database, and every migration has to run N times. Defers the same operational problem rather than avoiding it.
- *vs. app-layer-only enforcement:* a single missed `WHERE tenant_id = ...` clause in application code becomes a cross-tenant data leak — exactly the failure mode `AGENTS.md` §9 calls out. Enforcement needs to exist somewhere a forgotten filter can't bypass it.

**The chosen design, concretely:**
1. Every tenant-scoped table carries a `tenant_id` column (see roadmap step 042).
2. Postgres Row-Level Security policies are enabled on every such table (step 043) — the database itself refuses to return or write rows outside the session's tenant context, independent of application code correctness.
3. The application still filters by `tenant_id` explicitly in its repository layer (step 045) and has a dedicated test suite proving cross-tenant queries fail (steps 046, 057) — defense-in-depth, not reliance on RLS alone, per `AGENTS.md` §9 "perform defense-in-depth rather than relying on a single validation layer."
4. Tenant context is resolved once per request, from the authenticated session, by dedicated middleware (step 044) — never trusted from a client-supplied parameter.

**Tradeoff accepted:** Weaker blast-radius containment than physical database-per-tenant (a Postgres-level bug or a misconfigured superuser connection could theoretically cross tenants, versus a fully separate database). Accepted because RLS + app-layer + tests is a well-understood, widely-deployed pattern (this is how most multi-tenant SaaS at this scale actually runs), and because the operational cost of true physical isolation isn't justified at current or near-term scale.

**Implementation pitfall found and fixed while building the first tenant-scoped table (step 038):** Postgres superusers — and the `POSTGRES_USER` bootstrap role the official image always creates as one — bypass Row-Level Security unconditionally, `FORCE ROW LEVEL SECURITY` notwithstanding. An early version of this table's migration was applied and manually verified using that bootstrap role and appeared to leak data across tenants in testing; the RLS policy itself was correct, the connection just wasn't subject to it. Fixed by introducing a second, deliberately unprivileged Postgres role (`agentforge_app` — no `BYPASSRLS`, not a superuser, not a table owner) that the running application connects as (`DATABASE_URL`), while migrations continue to run as the bootstrap superuser (`DATABASE_MIGRATIONS_URL`), since DDL needs elevated rights. See `infra/postgres/init/01-app-role.sql`, `apps/api/config.py`, and `apps/api/tests/test_tenant_isolation.py` (which asserts against the real least-privilege connection, not the superuser one — testing RLS through a superuser connection would silently pass regardless of whether the policy works at all).

## Consequences
- Every new table added to the schema from Milestone 1 onward must decide explicitly whether it's tenant-scoped, and if so, get a `tenant_id` column + RLS policy as part of the same migration — not bolted on later.
- Vector store isolation (pgvector, per ADR-0001) follows the same pattern: `tenant_id` on the `Chunk` table, filtered at both the RLS and application layer, per roadmap step 132.
- Platform-super-admin cross-tenant views (needed for the platform administration layer, `AGENTS.md` §7) are the one intentional exception — they must go through an explicitly audited, separately-reviewed code path, not the standard tenant-scoped repository layer.

## Future migration path
If a specific enterprise customer contractually requires physical database isolation (data residency, extreme compliance requirements), that customer can be moved to a dedicated database using the same schema — the `tenant_id`-scoped design doesn't prevent this per-tenant, it just isn't the default for every tenant.
