from fastapi import FastAPI

from config import settings
from errors import register_exception_handlers
from logging_config import configure_logging, get_logger
from routers import auth, invitation, mfa, oauth, organization, security_settings, workspace

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="AgentForge API")
register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(mfa.router)
app.include_router(oauth.router)
app.include_router(organization.router)
app.include_router(workspace.router)
app.include_router(invitation.router)
app.include_router(invitation.accept_router)
app.include_router(security_settings.router)


@app.get("/health")
def health() -> dict[str, str]:
    logger.info("health_check_requested", environment=settings.environment)
    return {"status": "ok"}
