# syntax=docker/dockerfile:1
#
# Monorepo-aware: must be built from the REPO ROOT so it can see
# pnpm-workspace.yaml, pnpm-lock.yaml, and packages/shared, e.g.:
#   docker build -f apps/web/Dockerfile -t agentforge-web .

FROM node:22-alpine AS base
RUN corepack enable

FROM base AS deps
WORKDIR /repo
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json* ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared/package.json packages/shared/package.json
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY . .
# NEXT_PUBLIC_* vars are inlined into the client bundle at BUILD time
# (Next.js's own static replacement of process.env.NEXT_PUBLIC_API_URL,
# see apps/web/lib/api.ts) -- setting this as a container ENV at
# `docker run` time has no effect once the bundle already exists, so it
# must be a real build ARG, passed through docker-compose.prod.yml's
# own `build.args` (roadmap step 268).
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN pnpm --filter @agentforge/web run build

FROM base AS runtime
RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /app

COPY --from=builder --chown=app:app /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=app:app /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=app:app /repo/apps/web/public ./apps/web/public

USER app
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD node -e "fetch('http://localhost:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "apps/web/server.js"]
