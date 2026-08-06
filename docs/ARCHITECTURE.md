# AgentForge Architecture

This document describes the system **as implemented**, not as aspired to — it grows one section at a time as each subsystem lands, per the checkpoints built into `docs/ROADMAP.md`. For the full product/engineering vision this architecture serves, see [`AGENTS.md`](../AGENTS.md). For why specific technologies were chosen, see [`docs/adr/`](adr/).

## Status

Foundation milestone in progress. Sections below are filled in as the corresponding roadmap milestone completes — an empty section means that subsystem doesn't exist yet, not that it was forgotten.

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
- See the root `Makefile` for common commands.

## Multi-tenancy

_To be filled in as Milestone 1 (Multi-Tenancy Core) lands — see `docs/adr/0003-multi-tenancy-isolation-strategy.md`._

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
