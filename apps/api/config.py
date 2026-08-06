"""Centralized application configuration.

All configuration is read from environment variables (see .env.example)
through this single Settings object — no scattered os.environ.get() calls
elsewhere in the codebase, per AGENTS.md's configuration-management guidance.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Long enough (32+ bytes) that PyJWT doesn't warn about weak HMAC key
# length even if a dev never overrides it locally — but still obviously
# a placeholder, and _PLACEHOLDER_SECRETS below stops it reaching prod.
_PLACEHOLDER_SECRET = "change-me-to-a-random-value-at-least-32-bytes-long"
_PLACEHOLDER_SECRETS = frozenset({_PLACEHOLDER_SECRET})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "info"
    secret_key: str = _PLACEHOLDER_SECRET

    # Least-privilege role — no BYPASSRLS, not a superuser, not the table
    # owner — so Row-Level Security policies actually apply. Used by the
    # application at runtime (db.py). See infra/postgres/init/01-app-role.sql
    # and docs/adr/0003-multi-tenancy-isolation-strategy.md.
    database_url: str = (
        "postgresql+asyncpg://agentforge_app:agentforge_app@localhost:5432/agentforge"
    )

    # Bootstrap superuser — needed for DDL. Used only by Alembic
    # (migrations/env.py), never by the running application.
    database_migrations_url: str = (
        "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge"
    )

    # SQLAlchemy async engine pool sizing (ignored in tests — see db.py,
    # which uses NullPool there regardless of these values). Defaults are
    # conservative for local dev; tune per-deployment via env vars, not by
    # editing these numbers.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800

    redis_url: str = "redis://localhost:6379/0"

    storage_endpoint_url: str = "http://localhost:9000"
    storage_access_key: str = "agentforge"
    storage_secret_key: str = "agentforge123"
    storage_bucket: str = "agentforge-dev"

    openai_api_key: str = ""
    anthropic_api_key: str = ""

    jwt_secret: str = _PLACEHOLDER_SECRET
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 30

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @model_validator(mode="after")
    def _reject_placeholder_secrets_in_production(self) -> Self:
        # Fail at startup, not silently in production — AGENTS.md SECTION 9
        # treats insecure defaults as a design bug, not an ops footnote.
        if self.environment == "production":
            if self.secret_key in _PLACEHOLDER_SECRETS:
                raise ValueError("SECRET_KEY is still the placeholder value — set a real secret.")
            if self.jwt_secret in _PLACEHOLDER_SECRETS:
                raise ValueError("JWT_SECRET is still the placeholder value — set a real secret.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Convenience import: `from config import settings`.
settings: Settings = get_settings()
