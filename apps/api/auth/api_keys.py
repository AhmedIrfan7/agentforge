"""API key generation (roadmap step 241) -- same "random + SHA-256 hash
for exact-match lookup" shape auth/verification.py already established
for invitation/verification tokens, plus a plaintext prefix (stored on
the model, never the raw key itself) so a list view can identify which
key is which. Its own file, not verification.py -- an API key is a
standing, revocable, org-managed credential, not a short-lived "prove
you clicked a link" token, the same "separate concept, separate home"
reasoning Invitation already got its own model instead of reusing
VerificationToken.
"""

import hashlib
import secrets

_KEY_PREFIX = "afk_live_"
_PREFIX_DISPLAY_CHARS = 12


def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, key_hash, key_prefix). raw_key is shown to the
    caller exactly once, at creation -- nothing after this call ever
    has enough information to reconstruct it."""
    raw_key = _KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:_PREFIX_DISPLAY_CHARS]
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
