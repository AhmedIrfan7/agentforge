# @agentforge/shared

Cross-app TypeScript types and contracts shared between `apps/web` and `apps/widget`.

Consumed as source directly (no build step) — both consumers bundle it themselves. Once `apps/api` exposes an OpenAPI schema, generated types should live here instead of hand-duplicated ones.
