"""Centralized application configuration.

All configuration is read from environment variables (see .env.example)
through this single Settings object — no scattered os.environ.get() calls
elsewhere in the codebase, per AGENTS.md's configuration-management guidance.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "info"
    secret_key: str = "change-me-to-a-random-value"

    database_url: str = "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge"
    redis_url: str = "redis://localhost:6379/0"

    storage_endpoint_url: str = "http://localhost:9000"
    storage_access_key: str = "agentforge"
    storage_secret_key: str = "agentforge123"
    storage_bucket: str = "agentforge-dev"

    openai_api_key: str = ""
    anthropic_api_key: str = ""

    jwt_secret: str = "change-me-to-a-random-value"
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 30

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Convenience import: `from config import settings`.
settings: Settings = get_settings()
