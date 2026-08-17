import asyncio

import redis as sync_redis
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import settings
from db import get_session
from error_tracking import setup_error_tracking
from errors import register_exception_handlers
from logging_config import configure_logging, get_logger
from metrics import register_metrics_middleware, render_metrics
from observability import instrument_fastapi_app, setup_tracing
from routers import (
    analytics,
    api_key,
    assistant,
    audit_log,
    auth,
    conversation,
    document,
    invitation,
    knowledge_base,
    membership,
    memory,
    mfa,
    oauth,
    organization,
    platform_admin,
    public_conversation,
    public_voice,
    retrieval,
    security_settings,
    system_health,
    workspace,
)
from schemas.health import HealthRead, ReadinessCheck, ReadinessRead

configure_logging()
logger = get_logger(__name__)
setup_error_tracking(service_name="agentforge-api")
setup_tracing(service_name="agentforge-api")

app = FastAPI(title="AgentForge API")
instrument_fastapi_app(app)

# Wide open, deliberately: every real JSON API route in this codebase
# authenticates via a Bearer token attached by the caller's own JS
# (see auth/jwt.py -- there is no cookie-based session anywhere for
# an actual API route; routers/oauth.py's CSRF state cookie belongs to
# a top-level browser redirect, which CORS never gates in the first
# place). `allow_credentials=False` is what makes a wildcard origin
# safe here -- a malicious page can point a cross-origin fetch at this
# API, but it can never get the browser to auto-attach a real user's
# credentials the way it could for a cookie-authenticated API. The
# embeddable-widget deployment channel (routers/public_conversation.py,
# step 192) needs exactly this: an anonymous visitor's browser, running
# a widget script embedded on ANY third-party site, calling this API
# from an origin that can never be known in advance -- the same reason
# `apps/web`'s own real chat UI shell (step 194, a different, same-
# origin-limited caller) surfaced the gap live in the first place: with
# no CORS configured at all, even a same-product, first-party dev
# server on a different localhost port was silently blocked.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_metrics_middleware(app)
register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(mfa.router)
app.include_router(oauth.router)
app.include_router(organization.router)
app.include_router(workspace.router)
app.include_router(invitation.router)
app.include_router(invitation.accept_router)
app.include_router(membership.router)
app.include_router(api_key.router)
app.include_router(analytics.router)
app.include_router(security_settings.router)
app.include_router(audit_log.router)
app.include_router(system_health.router)
app.include_router(platform_admin.router)
app.include_router(knowledge_base.router)
app.include_router(document.router)
app.include_router(retrieval.router)
app.include_router(assistant.router)
app.include_router(conversation.router)
app.include_router(public_conversation.router)
app.include_router(public_voice.router)
app.include_router(memory.router)


@app.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    logger.info("health_check_requested", environment=settings.environment)
    return HealthRead(status="ok")


def _ping_redis() -> None:
    # A short-lived plain sync redis-py connection, not redis_client.py's
    # own async singleton -- that async client is a single connection
    # bound to whichever event loop first touches it, and this endpoint
    # is exercised via real HTTP through Starlette TestClient's own
    # internal portal loop (different from pytest's own test loop),
    # confirmed live to throw "Event loop is closed" exactly like
    # routers/system_health.py's own docstring already documents for
    # the identical root cause. A short-lived sync connection has no
    # loop to bind to, sidestepping the whole class of problem.
    sync_client = sync_redis.from_url(settings.redis_url)
    try:
        sync_client.ping()
    finally:
        sync_client.close()


@app.get("/ready", response_model=ReadinessRead)
async def readiness(response: Response) -> ReadinessRead:
    # Distinct from /health (roadmap step 273): /health is a pure
    # liveness check -- is the process itself alive -- and stays cheap
    # and dependency-free on purpose, since it's what both Dockerfiles'
    # own HEALTHCHECK directives and docker-build.yml's CI smoke tests
    # already rely on; changing ITS behavior to depend on Postgres/Redis
    # would make container restart policies flap on a brief dependency
    # blip, the wrong failure mode for a liveness probe. /ready answers
    # a genuinely different question -- can this instance actually serve
    # a real request right now -- for a real reverse proxy/load balancer
    # to route traffic away from an instance that can't, without killing
    # it. Real checks, not assumed: a real `SELECT 1` (no tenant context
    # needed, touches no tenant-scoped table) and a real Redis PING.
    database_ok = True
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
        logger.exception("readiness_check_database_failed")

    redis_ok = True
    try:
        await asyncio.to_thread(_ping_redis)
    except Exception:
        redis_ok = False
        logger.exception("readiness_check_redis_failed")

    ready = database_ok and redis_ok
    if not ready:
        response.status_code = 503
    return ReadinessRead(
        status="ready" if ready else "not_ready",
        checks=ReadinessCheck(database=database_ok, redis=redis_ok),
    )


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return render_metrics()
