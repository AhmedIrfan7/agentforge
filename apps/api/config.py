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

# Must be a syntactically valid Fernet key (32 raw bytes, urlsafe-base64
# encoded) so Fernet(mfa_encryption_key) doesn't crash at import time even
# with the placeholder still set — this decodes to the obviously-fake
# ASCII string "change-me-to-a-real-32-byte-key!". Generate a real one
# with `python -c "from cryptography.fernet import Fernet;
# print(Fernet.generate_key().decode())"`.
_PLACEHOLDER_MFA_KEY = "Y2hhbmdlLW1lLXRvLWEtcmVhbC0zMi1ieXRlLWtleSE="

_PLACEHOLDER_SECRETS = frozenset({_PLACEHOLDER_SECRET, _PLACEHOLDER_MFA_KEY})


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

    # Bootstrap superuser — needed for DDL. Used by Alembic
    # (migrations/env.py), and, as of step 110, by
    # vector_maintenance.py's REINDEX CONCURRENTLY task — REINDEX
    # requires index ownership on Postgres 16 (the MAINTAIN privilege
    # that would let a non-owner role do this doesn't exist until
    # Postgres 17), confirmed live (`agentforge_app` gets `ERROR: must
    # be owner of index`). REINDEX touches no tenant data (it rebuilds
    # an index structure, doesn't read/return rows), so this is an
    # honest, narrow exception to "the running application only uses
    # database_url" — a maintenance operation, not a data-access one.
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

    # Anonymous-session tokens (roadmap step 192) -- a pre-auth widget
    # visitor's proof of ownership over one specific Conversation, same
    # "how long should a returning visitor still be recognized" question
    # jwt_refresh_token_ttl_days already answers for real accounts, so it
    # gets the same 30-day answer rather than a separately-tuned guess.
    anonymous_session_ttl_days: int = 30

    # Used to build links in emails (verify-email, magic-link,
    # password-reset). apps/web doesn't have routes for these yet — the
    # links are logged (email.py is a stub), not clicked, until it does.
    app_base_url: str = "http://localhost:3000"

    # Google OAuth (roadmap step 076). Empty by default: unset, Google
    # simply rejects the request at the authorize step (fails closed, not
    # silently insecure) — no reason to gate this behind the placeholder-
    # secret production check the way jwt_secret/secret_key are, since an
    # empty client_secret can't be used to forge anything, only to fail.
    # google_redirect_uri must exactly match a URI registered in Google
    # Cloud Console, and points at this API directly (not app_base_url,
    # the frontend's origin) — see auth/oauth.py's module docstring for
    # why the callback lives here rather than on the frontend.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # MFA/TOTP (roadmap step 078). Symmetric key encrypting each user's
    # TOTP secret at rest (auth/mfa.py) — unlike a password hash, a TOTP
    # secret must be recoverable in plaintext to verify a code against it,
    # so it's encrypted rather than hashed. Gated by the same placeholder
    # check as jwt_secret/secret_key: a real secret is directly usable to
    # decrypt every enrolled user's TOTP secret, unlike an empty Google
    # client_secret, which can only fail.
    mfa_encryption_key: str = _PLACEHOLDER_MFA_KEY
    mfa_ticket_ttl_minutes: int = 10

    # Upload size limit (roadmap step 086). 50 MB — generous for real
    # documents (PDFs/DOCXs/etc. rarely approach this) while still
    # bounding how much any single upload can force into memory
    # (validation.py:read_upload_content enforces this while streaming
    # the file in, not after already buffering it all — the whole point
    # of a size limit is defeated if the check happens after the fact).
    max_upload_size_bytes: int = 52_428_800

    # Virus/malware scan (roadmap step 087). clamd (ClamAV's daemon) --
    # antivirus.py speaks its INSTREAM protocol directly over this
    # host/port rather than through a client library. No disable toggle:
    # like database_url/storage_endpoint_url, this is required
    # infrastructure, not an optional feature.
    clamav_host: str = "localhost"
    clamav_port: int = 3310

    # OpenTelemetry distributed tracing (roadmap step 256). Empty by
    # default -- same "real, tested code, genuinely inert until a real
    # endpoint is configured" pattern openai_api_key/anthropic_api_key
    # already established (see ADR-0004): no real OTLP collector
    # (Jaeger, Honeycomb, Datadog, etc.) exists for this project yet.
    # See observability.py for what happens with no endpoint configured.
    otel_exporter_otlp_endpoint: str = ""

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
            if self.mfa_encryption_key in _PLACEHOLDER_SECRETS:
                raise ValueError(
                    "MFA_ENCRYPTION_KEY is still the placeholder value — set a real Fernet key."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Convenience import: `from config import settings`.
settings: Settings = get_settings()
