"""Centralized error tracking (roadmap step 258; AGENTS.md's own real,
distributed "ERROR ANALYTICS" section names API/Agent/Infrastructure/
Background-worker failures by name, and "OBSERVABILITY STACK" says
"Administrators should detect problems before users do"). sentry-sdk --
the roadmap step's own literal wording is "Sentry or equivalent", and
this is the real, dominant equivalent.

Same "real code, genuinely inert until a real DSN is configured" pattern
already established for otel_exporter_otlp_endpoint (step 256) and the
LLM provider API keys (ADR-0004): no real Sentry project exists for this
codebase yet. Confirmed live: sentry_sdk.init(dsn=None) leaves
client.transport as None, and every sentry_sdk capture call becomes a
real, safe no-op (never raises, never tries to reach a network endpoint
that was never configured) rather than crashing at import time.

No explicit `sentry_sdk.capture_exception()` calls anywhere in this
codebase, by design, confirmed live rather than assumed:
FastApiIntegration/StarletteIntegration already auto-capture any
exception that falls through to the generic `Exception` handler
(errors.py's own `handle_unexpected` -- real, unexpected 500s) even
though that handler catches it and returns its own clean JSONResponse
rather than re-raising; a LIVE test proved the integration hooks the
ASGI layer above FastAPI's own exception-handler dispatch, not the
handler's return value. The SAME live test proved `AppError` subclasses
(NotFoundError, UnauthorizedError, TooManyRequestsError, etc. --
errors.py's own `@app.exception_handler(AppError)`) are correctly NOT
captured: they're expected, client-caused outcomes with their own
specific registered handler, not operational failures worth paging on --
capturing every 404/401/429 would drown real signal in noise.
CeleryIntegration is the same story on the worker side: a live test
proved it auto-captures a real task failure with no extra code here.
"""

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from config import settings


def setup_error_tracking(*, service_name: str) -> None:
    sentry_sdk.init(
        dsn=settings.sentry_dsn or None,
        environment=settings.environment,
        server_name=service_name,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            CeleryIntegration(),
            SqlalchemyIntegration(),
        ],
        # Multi-tenant SaaS with real user data (AGENTS.md SECTION 9) --
        # request bodies/headers/user data must not flow to a third-party
        # service by default. This is also sentry-sdk's own default, kept
        # explicit here so it can't silently flip if that default ever
        # changes upstream.
        send_default_pii=False,
    )
