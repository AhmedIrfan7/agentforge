# Self-Hosted Deployment

Roadmap step 269. A real, single-host deployment using
[`docker-compose.prod.yml`](../docker-compose.prod.yml) (step 268) and the
production Dockerfiles it builds from (step 267). Every command below was
actually run against this stack while writing this doc — not copied from a
generic template.

This is honestly scoped: one host, Docker Compose, no orchestration platform,
no managed cloud services. If you need horizontal scaling, managed Postgres,
or multi-region — that's a different deployment shape this doc doesn't cover
yet (see `docs/ARCHITECTURE.md`'s own "Infrastructure & deployment" section,
still growing through the rest of Milestone 11).

## Prerequisites

- Docker + Docker Compose v2 (`docker compose version`).
- A host with enough RAM/CPU for Postgres, Redis, MinIO, ClamAV, the API,
  a Celery worker, and the web app running simultaneously — 4 GB RAM is a
  reasonable floor for light traffic; ClamAV alone wants ~1–2 GB.
- A domain name if you want a real, non-IP URL (recommended — see TLS below).

## 1. Clone and configure

```bash
git clone https://github.com/AhmedIrfan7/agentforge.git
cd agentforge
cp .env.prod.example .env.prod
```

Fill in every value in `.env.prod` — see that file's own comments for exactly
what each one is and how to generate it. In particular:

- `POSTGRES_APP_PASSWORD` must match whatever password you set for the
  `agentforge_app` role in
  [`infra/postgres/init/01-app-role.sql`](../infra/postgres/init/01-app-role.sql)
  — edit that file's own `CREATE ROLE agentforge_app WITH LOGIN PASSWORD
  '...'` line to a real password, it does NOT read `.env.prod` (Postgres init
  scripts run before the app container, or `.env.prod`, even exist to it).
- `SECRET_KEY`/`JWT_SECRET`/`MFA_ENCRYPTION_KEY` are checked by `config.py`'s
  own startup validator — the app refuses to boot with `ENVIRONMENT=production`
  (which `docker-compose.prod.yml` sets) if any of these are still the dev
  placeholder values, so there's no way to accidentally ship real user data
  behind a guessable secret.

## 2. Build and start

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

This builds `api`, `worker`, and `web` from their real Dockerfiles and starts
everything (`postgres`, `redis`, `minio`, `clamav`, `api`, `worker`, `web`) in
the right order — `api`/`worker` both wait on `postgres`/`redis`/`minio`/
`clamav` reporting healthy first (real `depends_on: condition: service_healthy`,
not just "started").

## 3. Run migrations

The Dockerfile's own `CMD` only starts `uvicorn` — it deliberately does NOT
run migrations automatically on every container start (a bad idea with
multiple replicas racing to apply the same migration). Run them once,
explicitly, against the running `api` container's own image:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api alembic upgrade head
```

Note: this is `alembic upgrade head`, not `uv run alembic upgrade head` — the
production image's runtime stage doesn't have `uv` itself, only the app's own
`.venv` (already on `PATH`). Confirmed live against a real running container.

## 4. TLS / reverse proxy

**Nothing in this stack terminates HTTPS.** `api` serves plain HTTP on 8000,
`web` on 3000. Put a real reverse proxy in front of both on the host (Caddy,
nginx, or Traefik are all reasonable, standard choices — Caddy is the least
config for a first deployment, since it gets a real Let's Encrypt certificate
automatically from just a domain name) and only expose 80/443 to the internet,
not 8000/3000/5432/6379/9000/9001/3310 directly.

## 5. Verify it's actually working

```bash
curl -f http://localhost:8000/health   # {"status":"ok"}
curl -f http://localhost:8000/ready    # {"status":"ready","checks":{"database":true,"redis":true}}
curl -f http://localhost:3000/         # real HTML
```

`/health` and `/ready` answer different questions (step 273) — `/health`
is a pure liveness check (is the process alive; both Dockerfiles' own
`HEALTHCHECK` directives use this, and it stays that way on purpose so a
brief Postgres/Redis blip doesn't cause a container restart). `/ready`
does real Postgres/Redis checks and returns 503 if either fails — point
your reverse proxy's own health check at `/ready` if it should stop
routing traffic to an instance that can't actually serve a request,
without killing that instance the way a failed liveness check would.

## Ongoing operations

- **Backups**: `scripts/backup.sh`/`scripts/restore-drill.sh` (step 265) work
  the same way here as in local dev — they target the same real
  `agentforge-postgres`/MinIO data. Run `make backup` on a real schedule (a
  cron job — the scripts themselves aren't scheduled automatically yet, see
  `docs/runbooks/incident-response.md`'s own "Known gaps").
- **Observability**: set `OTEL_EXPORTER_OTLP_ENDPOINT`/`SENTRY_DSN` in
  `.env.prod` to point at a real collector/Sentry project — both are real,
  tested code that's genuinely inert until configured (steps 256/258).
  `GET /metrics` (step 257) is real Prometheus output the moment the `api`
  container is up, no extra config needed.
- **Incidents**: [`docs/runbooks/incident-response.md`](runbooks/incident-response.md)
  (step 263).
- **Security issues**: [`SECURITY.md`](../SECURITY.md) (step 264).

## Updating

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api alembic upgrade head
```

`--build` rebuilds only what changed (Docker's own layer cache); running
migrations again is always safe (`alembic upgrade head` is idempotent —
already-applied migrations are skipped).
