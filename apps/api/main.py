from fastapi import FastAPI

from config import settings
from logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="AgentForge API")


@app.get("/health")
def health() -> dict[str, str]:
    logger.info("health_check_requested", environment=settings.environment)
    return {"status": "ok"}
