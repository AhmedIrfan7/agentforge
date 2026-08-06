# ADR-0002: Monorepo vs Multi-repo

## Status
Accepted — 2026-08-06

## Problem
AgentForge is split into `apps/api`, `apps/web`, `apps/widget`, and `packages/shared`. Should these live in one repository or several? This is worth its own record beyond the summary in ADR-0001 because it shapes CI design, release process, and how the project scales past solo development.

## Decisions

### Repository layout: single monorepo
**Alternatives considered:**
- **Multi-repo**, one repository per app/service, coordinated via published packages or git submodules.
- **Monorepo with a build-orchestration tool** (Turborepo/Nx) from day one.

**Why single monorepo (no orchestration tool yet):** With one developer and four small, tightly-related packages, a plain `pnpm` workspace plus `uv` gives atomic cross-cutting commits (an API contract change and its frontend consumer land together, reviewed together) without adding a build-graph tool whose caching/orchestration value only shows up once CI runtimes or team size actually justify it. Matches `AGENTS.md` §4's instruction to avoid unnecessary complexity before it's earned.

**Tradeoff accepted:** CI currently runs full jobs for both `apps/api` and `apps/web` on every push (`.github/workflows/lint.yml`, `api-tests.yml`, `web-tests.yml`), even when only one side changed. Acceptable at current size; path-filtering (`paths:` triggers, or adopting Turborepo/Nx for affected-package detection) is the documented next step once build times start to hurt, not before.

## Consequences
- A change spanning `apps/api` (schema) and `apps/web` (consumer) is one commit, one PR, one review — not two repos with a version-bump dance between them.
- `packages/shared` has no publish/versioning step; it's just workspace-linked source. Fine while it only serves `apps/web` and `apps/widget` inside this repo.
- If/when a team grows into independently-releasable services, or CI time becomes a real bottleneck, that's a trigger for revisiting this ADR — not a reason to preemptively split now.

## Future migration path
Split a specific app into its own repository if and when it needs an independent release cadence, its own access controls, or its own CI budget that the monorepo can't reasonably give it. `packages/shared` would need to become a versioned, published package at that point rather than workspace-linked source.
