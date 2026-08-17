# Incident Response Runbook

Roadmap step 263. Grounded in the real architecture as it exists today (see
[`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)) — this project has no real production
deployment yet (Milestone 11, steps 267–280, isn't built), so "incident" here means a
failure of the local/self-hosted stack (Docker Compose: Postgres+pgvector, Redis, MinIO,
ClamAV, the API process, one or more Celery workers). Update this doc as Milestone 11
lands real infra to respond to instead of speculating about infrastructure that doesn't
exist yet — see each section's own "Once Milestone 11 lands" note.

## Severity

- **SEV1** — the API is down, or tenant data is being read/written across tenant
  boundaries (an RLS bypass). Stop the bleeding first, investigate second.
- **SEV2** — a real feature is broken for some/all tenants (uploads failing, search
  returning nothing) but the platform itself is reachable and tenant isolation holds.
- **SEV3** — degraded but working (elevated latency, one provider integration down,
  the worker queue backing up but still draining).

## General response sequence

1. **Detect.** `GET /system-health` (step 248, `require_platform_admin`-gated) reports
   real queue depth, worker count, and provider-key-configured status in one call.
   `GET /metrics` (step 257) has the real Prometheus counters/histograms. Once
   `SENTRY_DSN`/`OTEL_EXPORTER_OTLP_ENDPOINT` are configured for a real deployment
   (both real, tested, but inert without one — steps 256/258), Sentry and a trace
   backend are the first places to look instead of grepping logs by hand.
2. **Triage.** Which severity? Which tenants are affected — one org, or everyone?
   Check `AuditLog` (`routers/audit_log.py`, per-org viewer) for anything relevant
   an admin already sees.
3. **Mitigate.** Stop active harm first — this can mean rolling back a bad deploy
   (once Milestone 11 has a real deploy pipeline), disabling a broken feature flag if
   one exists, or (rare, last resort) taking a specific tenant's write path offline
   rather than the whole platform.
4. **Resolve.** Fix the real root cause, not just the symptom.
5. **Post-incident.** Write down what happened, why, and what changes (code, alerting,
   or this runbook) would have caught it sooner or prevented it. AGENTS.md's own
   "ERROR ANALYTICS" section calls this out directly: "Identify recurring patterns.
   Recommend improvements."

## Database failure (Postgres)

Postgres is also the vector store (pgvector) — a database failure is a vector-search
failure too, not two separate incidents.

- Check the container: `docker compose ps postgres`, `docker compose logs postgres`.
- Confirm it's actually unreachable, not just slow: `docker exec agentforge-postgres
  pg_isready -U agentforge -d agentforge`.
- If the container crashed and restarted, check for a corrupted WAL/data directory
  before assuming it's healthy again — `docker compose logs postgres` on a fresh
  start will show recovery errors if there's real corruption.
- RLS is `FORCE ROW LEVEL SECURITY` with no bypass mechanism anywhere in this codebase
  (`docs/adr/0003-multi-tenancy-isolation-strategy.md`) — if you ever see cross-tenant
  data in a response, that is automatically a SEV1, not a SEV2, regardless of how
  small the blast radius looks.
- **Once Milestone 11 lands:** this section needs real managed-Postgres failover
  procedures (read replica promotion, point-in-time recovery) — there's no such thing
  today, only a single local container.

## Storage failure (MinIO / object storage)

- `docker compose ps minio`, `docker compose logs minio`.
- Document uploads will fail at `storage.py:upload_file`; existing documents' chunks
  (already extracted into Postgres) stay queryable even if the ORIGINAL file in
  storage is temporarily unreachable — search/retrieval doesn't re-read the raw file.
- **Once Milestone 11 lands:** this becomes a real S3 (or S3-compatible) outage —
  check the provider's own status page first; nothing in this app can route around a
  real provider-side S3 outage today.

## Queue / worker failure (Redis + Celery)

- `GET /system-health` reports real queue depth (`LLEN` on the `celery` list key) and
  worker count (`celery_app.control.inspect().ping()`) in one call — start here.
- `docker compose logs redis`.
- If workers are running but the queue is growing: check `GET /metrics` for
  `celery_task_total{status="failure"}` — a real, currently-failing task class is more
  likely than the workers being wedged.
- If no workers are running at all, restart with:
  `uv run celery -A celery_app worker --loglevel=info` (add `--pool=solo` on Windows).
- A large backlog of stale, unconsumed tasks in Redis (from a period with no worker
  running) is real, encountered, harmless-but-noisy local-dev debt — `celery -A
  celery_app purge -f` clears it; only do this in a real deployment after confirming
  those tasks are genuinely unrecoverable, not just slow.

## LLM/embedding provider outage

- `GET /system-health`'s `providers` field only reports whether an API key is
  *configured*, not live reachability (a live probe would always fail in this
  project's own dev/CI environment, which has no real key set — see the endpoint's
  own docstring). A real outage shows up as a specific provider's own error surfacing
  through `AgentExecutionLog`/Sentry, not through `/system-health`.
- Embedding failures leave a document in `embedding_failed` status
  (`pipeline_status.py`) rather than silently succeeding with no vectors — that
  status itself is the signal, check for a spike in it.
- No automatic provider failover exists (single-provider `embeddings/openai.py` /
  `llm/base.py` implementations) — a real outage is a real incident until the
  provider recovers or the config is manually pointed at a different one.

## Accidental deletion / corrupted data

- Every tenant-scoped table's own FK cascades are real and intentional (e.g.
  `Chunk`/`DocumentVersion` cascade on `Document` delete) — a delete you didn't
  expect the blast radius of is more likely a real cascade working as designed than
  a bug. Check the model's own `ondelete=` before assuming corruption.
- There is **no backup/restore automation yet** — roadmap step 265 ("Add backup
  automation + restore-drill script") is the step that builds this. Until it lands,
  recovering deleted data means restoring the entire local Postgres data volume from
  whatever manual backup exists, which is not a currently-tested or currently-real
  procedure. Treat "did we actually test restoring from backup" as an open, named
  gap, not an assumption — this doc will link to the real restore-drill script once
  step 265 exists.

## Security incident (suspected breach, auth bypass, cross-tenant leak)

- Automatically SEV1.
- `tests/test_security_suite.py` (step 262) is the permanent regression suite for the
  specific classes this section cares about most (auth bypass, injection) — if an
  incident matches one of its scenarios, that's a signal the regression coverage
  itself has a gap, not just that this one instance needs fixing.
- Check `AuditLog` rows for `security.permission_denied` / `security.cross_tenant_attempt`
  (step 255) and structured `login_failed` / `repeated_failed_login_detected` (step 259)
  events around the incident window — these exist specifically so an incident isn't
  reconstructed from scratch after the fact.
- Rotate `JWT_SECRET`/`SECRET_KEY`/`MFA_ENCRYPTION_KEY` if there's any suspicion a
  secret itself was exposed — this invalidates every existing session (see
  [`docs/adr/0004-secrets-management.md`](../adr/0004-secrets-management.md) for what
  each secret actually protects).
- Report responsible-disclosure findings per [`SECURITY.md`](../../SECURITY.md)
  (repo root, roadmap step 264).

## Known gaps (honest, not hidden)

- No backup automation or tested restore procedure yet (step 265).
- No real production deployment, so no real deploy-rollback procedure yet
  (Milestone 11, steps 267–280).
- No region redundancy — explicitly a "Future" item in AGENTS.md's own BACKUPS
  section, not attempted here.
- No live provider-reachability probing, by design (see `/system-health` section
  above) — a real outage is detected by its symptoms, not a health check.
