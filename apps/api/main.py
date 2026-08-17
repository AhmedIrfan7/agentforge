from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from errors import register_exception_handlers
from logging_config import configure_logging, get_logger
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
from schemas.health import HealthRead

configure_logging()
logger = get_logger(__name__)
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
