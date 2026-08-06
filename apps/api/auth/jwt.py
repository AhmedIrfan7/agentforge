"""Access-token issuing/verification (JWT) and refresh-token generation.

Access tokens are stateless JWTs (short-lived — config.jwt_access_token_ttl_minutes)
carrying only the user id; nothing tenant-specific goes in here, since a
user can belong to multiple organizations and which one applies is a
per-request concern (dependencies/tenant.py), not a per-login one.

Refresh tokens are opaque random strings, not JWTs — stored server-side
(models/session.py) so they can be revoked (logout, step 064) before
their natural expiry, which a stateless JWT can't be. Hashed with SHA-256
before storage: unlike passwords (auth/passwords.py), a refresh token
needs exact-match DB lookup, so it can't use a randomly-salted hash like
argon2 — but it's already 256 bits of secrets.token_urlsafe randomness,
so a fast deterministic hash is sufficient (nothing to brute-force; the
entropy is in the token, not in guessing it from a hash).
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from config import settings

_ALGORITHM = "HS256"


class TokenError(Exception):
    pass


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        # Standard JWT claim, not decoded/checked anywhere yet — but
        # without it, two tokens issued for the same user within the same
        # wall-clock second are byte-identical (iat/exp have second-level
        # granularity), which is harmless functionally but surprising, and
        # means no way to reference "this specific token" later
        # (step 064's logout-of-one-session needs exactly that).
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Returns the user id, or raises TokenError for any invalid/expired/
    wrong-type token — never leak *why* to the caller (AGENTS.md SECTION 9:
    error messages should not reveal internal validation details)."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired token.") from exc

    if payload.get("type") != "access":
        raise TokenError("Invalid or expired token.")

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError("Invalid or expired token.") from exc


def generate_refresh_token() -> tuple[str, str, datetime]:
    """Returns (raw_token, hash_for_storage, expires_at). Give the raw
    token to the client, store only the hash."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_refresh_token(raw_token)
    expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_ttl_days)
    return raw_token, token_hash, expires_at


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
