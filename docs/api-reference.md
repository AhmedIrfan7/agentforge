# API reference

The REST API's reference documentation is generated from the live
FastAPI app's own OpenAPI schema — nothing here is hand-written or
maintained separately from the actual route/schema code, so it can't
drift the way a hand-written endpoint list would.

## Browsing it

**Interactive (server running):**

- `GET /docs` — Swagger UI, grouped by tag (`auth`, `organizations`,
  `documents`, `retrieval`, etc.), with request/response schemas and a
  real "Try it out" form.
- `GET /redoc` — ReDoc, a read-only single-page reference, often easier
  to skim than Swagger UI for a large API.
- `GET /openapi.json` — the raw schema, if you want to feed it into
  another tool (Postman, an SDK generator, etc.).

**Static (no server needed):** [`docs/openapi.json`](openapi.json) is a
generated, checked-in copy of the same schema, for browsing the API
shape without running anything locally. It's a build artifact, not
hand-maintained — regenerate it after any router/schema change:

```bash
make api-openapi-export
```

(Equivalent to `cd apps/api && uv run python -m scripts.export_openapi`
— see `apps/api/scripts/export_openapi.py`.)

## What's covered, and what isn't

Every real HTTP route in `apps/api/routers/` is covered — 72 paths as of
this writing, tagged and grouped the same way `main.py`'s
`app.include_router()` calls register them (see
[`docs/extension-points.md`](extension-points.md) if you're adding a new
router and want it grouped sensibly).

**Not covered:** this API's one WebSocket route (`WS
/public/assistants/{id}/voice-sessions/{id}/audio`, real-time voice
audio streaming) — OpenAPI 3.0 has no representation for WebSocket
endpoints, so it's genuinely absent from `/docs`, `/redoc`, and
`openapi.json` alike, not an oversight in the generation. Its message
protocol is documented in the "Voice platform" section of
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) instead.

## Authentication in the interactive docs

Most routes require a Bearer token (`Authorization: Bearer <token>`,
issued by `POST /auth/login` or the OAuth flow). Swagger UI's
"Authorize" button accepts one directly; `public-chat`/`public-voice`
routes use a separate anonymous-session token instead, obtained from
their own first-call endpoints — see the "Embeddable widget" section of
`docs/ARCHITECTURE.md` for that flow.
