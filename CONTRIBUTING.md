# Contributing to AgentForge

## Current status

AgentForge is not yet open for external pull requests. The project is
actively developed against a public 300-step roadmap
([`docs/ROADMAP.md`](docs/ROADMAP.md)) and is currently in Milestone 12
(Open Source Readiness / Public Beta) — issue/PR templates, GitHub labels,
and a first tagged beta release are still landing (roadmap steps 283–293).
Opening PRs before those exist would mean contributors hitting an
undocumented, unstructured process; this file describes the real process
that will apply once they do, not a hypothetical future one.

Until then:

- **Bug reports and design feedback** on the direction in `AGENTS.md` /
  `docs/ROADMAP.md` are welcome via GitHub Issues.
- **Pull requests** will start being accepted once Milestone 12 completes.

## Dev setup

See the [README's own Quickstart](README.md#quickstart-local-development) —
not duplicated here, so there's one real, maintained copy of these steps
instead of two that can drift out of sync.

## Adding a provider or agent

Several subsystems (LLM, embeddings, voice STT/TTS, OAuth, agents) are
built behind a `Protocol` interface specifically so a new real
implementation doesn't require a rewrite. See
[`docs/extension-points.md`](docs/extension-points.md) for exactly which
ones, what's already there, and what implementing a new one looks like
in practice.

## Coding standards

Real, currently-enforced conventions — every one of these is checked by CI
(`.github/workflows/lint.yml`), not aspirational.

### `apps/api` (Python)

- [`ruff`](https://docs.astral.sh/ruff/) for linting and formatting — see
  `apps/api/pyproject.toml`'s own `[tool.ruff]` section for the exact rule
  set (`E`, `F`, `I`, `UP`, `B`, `SIM`, `C4`), 100-character line length,
  double-quote strings.
- `mypy --strict` — every function needs real type annotations; no
  `# type: ignore` without a comment explaining why (see any file in
  `apps/api` for real examples — an untyped third-party decorator is the
  most common legitimate reason).
- Real tests for real behavior. This codebase's own convention: prove a
  test actually catches the bug it claims to (deliberately reintroduce the
  bug, confirm the test fails, then re-fix) rather than trusting that a
  passing test means the invariant holds.

Run locally: `make api-lint` / `make api-format` / `make api-test`.

### `apps/web`, `apps/widget`, `packages/shared` (TypeScript)

- `eslint` + `prettier` — see each package's own `eslint.config.*` /
  `.prettierrc` for specifics.
- `tsc --noEmit` for type-checking (`apps/widget`'s own `pnpm run
  typecheck`; `apps/web` type-checks as part of its own build).

Run locally: `make web-lint` / `make web-format`, or `pnpm --filter
<package> run lint` for a specific package.

### Comments

Default to none. Only write a comment when the reasoning behind a decision
isn't obvious from the code itself — a non-obvious constraint, a bug a
naive approach would hit, why one option was chosen over a real alternative.
Never restate what the code already says.

### Commit messages

Present tense, imperative ("Add", not "Added"). Subject line under ~70
characters. The body explains **why**, not what — the diff already shows
what changed. A real excerpt, from this project's own history
(`git log --format=%B e99f418`):

```
Add system-health dashboard (step 248)

routers/system_health.py: GET /system-health, the first real check of
User.is_platform_admin since it was seeded -- AGENTS.md's own
OBSERVABILITY STACK section names "Worker status," "Queue health," and
"Provider status" by name [...]

Queue depth and worker status both run through one real, synchronous
check [...] Both use a short-lived sync redis-py connection (not the
app's own async redis_client singleton) inside one asyncio.to_thread
call -- that async client is bound to whichever event loop first
touches it, and Starlette TestClient's own internal portal loop made
that a real, reproducible "Event loop is closed" failure once this
endpoint's own tests exercised it through a real HTTP round trip
instead of a direct function call; a sync connection has no loop to
bind to.
```

## Pull request process (once open)

1. One focused change per PR — matches this project's own commit
   discipline (`AGENTS.md` SECTION 10: small, independently-testable,
   avoid "implement entire feature" changes).
2. CI must pass: Lint, API Tests, Web Tests, Widget Tests, Docker Build,
   CodeQL, Dependency Audit (see the badges in
   [`README.md`](README.md) for what each one checks).
3. Non-trivial architectural decisions get a real ADR in
   [`docs/adr/`](docs/adr/) — see the existing ones there for the format
   and the level of "why," not just "what."
4. Any change touching data access must preserve real multi-tenant
   isolation — see `AGENTS.md` §7/§9 and
   [`docs/adr/0003-multi-tenancy-isolation-strategy.md`](docs/adr/0003-multi-tenancy-isolation-strategy.md).
   A PR that weakens Row-Level Security isolation, even accidentally, is
   treated as a security bug, not a style preference.
5. A user-facing change (new capability, behavior change, notable fix)
   gets a line under [`CHANGELOG.md`](CHANGELOG.md)'s `[Unreleased]`
   section — internal refactors and test-only changes don't need one.

## Questions

Check [`FAQ.md`](FAQ.md) first — if it's not answered there, open a GitHub
Discussion or Issue on this repository.
