# Changelog

All notable changes to AgentForge are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## Versioning policy

**Project version** — `apps/api/pyproject.toml`, `apps/api/main.py`
(the FastAPI app's own `version=`), `apps/web/package.json`, and
`packages/shared/package.json` are kept in sync and currently at
`1.0.0`. This is the version a GitHub Release/tag refers to. Per
[SemVer](https://semver.org/), `1.0.0` is a real commitment: a breaking
change to the public API from here requires a major version bump, not a
silent change within a minor/patch release.

**Widget script version** — `apps/widget/package.json` (currently
`0.2.0`) is intentionally independent. It tracks the embeddable widget
script's own public embed contract (`v{version}/widget.js`, pinnable by
customers), not the project as a whole — bumped only when that contract
changes. See [`docs/embedding.md`](docs/embedding.md#pinning-a-specific-widget-version)
and `versions.json` on the published widget CDN for its real version
history.

## [Unreleased]

## [1.0.0] - 2026-08-17

All 300 steps of the public roadmap complete. A solo-built, self-reviewed
milestone, not an externally-audited or production-traffic-proven one —
see the [GitHub Release](https://github.com/AhmedIrfan7/agentforge/releases/tag/v1.0.0)
for the full, honestly-scoped notes.

### Added

- Real security review pass: 3 CodeQL alerts investigated and dismissed
  with documented reasoning, Dependabot vulnerability alerts and
  automated security fixes enabled, branch protection added to `main`.
- Closed a previously self-documented gap: `STORAGE_SECRET_KEY` now
  covered by the same production placeholder-rejection check as
  `SECRET_KEY`/`JWT_SECRET`/`MFA_ENCRYPTION_KEY`.
- Real performance benchmark script and documented local-dev latency
  numbers for the core API paths ([`docs/performance-benchmark.md`](docs/performance-benchmark.md)).
- The "Authentication & authorization" architecture doc section — empty
  since Milestone 2 — is now written.
- A working feedback-triage mechanism (`needs-triage` label + process).

## [0.1.0-beta] - 2026-08-17

First tagged release. See the [GitHub Release](https://github.com/AhmedIrfan7/agentforge/releases/tag/v0.1.0-beta) for the same notes.

### Added

- Multi-tenant organizations, workspaces, and role-based membership,
  isolated with Postgres Row-Level Security enforced again at the
  application layer.
- Email/password and Google OAuth authentication, with TOTP-based MFA.
- Document ingestion pipeline: upload, virus scanning, text extraction,
  automatic chunking-strategy selection, and embedding generation.
- Hybrid vector + keyword retrieval with reranking, citing real source
  chunks.
- Multi-agent orchestration (LangGraph) with per-agent execution
  tracing.
- Cross-conversation assistant memory.
- Real-time conversation engine for both authenticated callers and
  anonymous embeddable-widget visitors.
- Embeddable chat + voice widget, deployable via a single script tag.
- Voice platform: real-time speech-to-text/text-to-speech calls sharing
  the same conversation intelligence as chat, with barge-in support.
- Admin dashboard: assistant configuration, analytics, security
  settings, audit logs.
- Security hardening: tenant-keyed rate limiting and abuse detection,
  centralized error tracking, Prometheus metrics, CodeQL and dependency
  scanning in CI.
- Deployment infrastructure: Docker images, GitHub Actions CI/CD,
  staging/production deploy workflows, a Terraform reference
  deployment, and automated uptime monitoring.
- OpenAPI-generated API reference ([`docs/api-reference.md`](docs/api-reference.md)).
- Documented extension points for LLM/embedding/voice/OAuth providers
  and agents ([`docs/extension-points.md`](docs/extension-points.md)).
