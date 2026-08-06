"""Opaque token generation for verify-email / magic-link / password-reset —
same reasoning as auth/jwt.py's refresh tokens: random + SHA-256 hash for
exact-match lookup, since the entropy lives in the token, not in guessing
it from a hash.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

# Deliberately short-lived — these prove "you clicked a link in your
# email just now," not a standing credential. 1 hour matches common
# practice (verify-email/password-reset links) and is generous for a
# magic-link login too.
_TOKEN_TTL = timedelta(hours=1)


def generate_verification_token() -> tuple[str, str, datetime]:
    """Returns (raw_token, hash_for_storage, expires_at)."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_verification_token(raw_token)
    expires_at = datetime.now(UTC) + _TOKEN_TTL
    return raw_token, token_hash, expires_at


def hash_verification_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
