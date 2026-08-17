# @agentforge/shared

Cross-app TypeScript types and contracts shared between `apps/web` and `apps/widget`.

Consumed as source directly (no build step) — both consumers bundle it themselves. `apps/api` now exposes a real OpenAPI schema ([`docs/openapi.json`](../../docs/openapi.json), [`docs/api-reference.md`](../../docs/api-reference.md)) — generating types here from it instead of the current hand-duplicated ones would remove that duplication, but hasn't been done yet.
