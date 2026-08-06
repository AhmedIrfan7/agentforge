"""Redis-backed fixed-window rate limiting for auth endpoints
(AGENTS.md SECTION 9 "Rate Limiting" / "Abuse Prevention").

Per-client-IP for now — not per-account, since an unauthenticated
attacker doesn't need a real account to hammer signup/login, and the
email-sending endpoints (magic-link, password-reset) don't require one
either. Fixed window (INCR + EXPIRE-on-first-increment), not sliding —
simple, cheap, and good enough at this scale; a burst right at a window
boundary is an acceptable tradeoff for not needing a Lua script or
sorted-set bookkeeping.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request

from config import settings
from errors import TooManyRequestsError
from redis_client import redis_client


def rate_limit(
    *, key_prefix: str, limit: int, window_seconds: int
) -> Callable[[Request], Awaitable[None]]:
    async def dependency(request: Request) -> None:
        # Disabled under pytest: the test suite legitimately calls these
        # endpoints far more than any real client would (many tests touch
        # /auth/login, /auth/signup, etc. across dozens of files), all
        # from TestClient's fixed simulated IP, and Redis state persists
        # across test runs (nothing flushes it) — real limits here would
        # make the test suite flaky/order-dependent for reasons that have
        # nothing to do with what's actually being tested. Real
        # enforcement is proven directly by tests/test_rate_limit.py
        # against redis_client itself instead.
        if settings.environment == "test":
            return

        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{key_prefix}:{client_ip}"

        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_seconds)

        if count > limit:
            raise TooManyRequestsError("Too many requests. Please try again later.")

    return dependency
