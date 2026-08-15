"""Redis-backed fixed-window rate limiting for auth endpoints and,
as of roadmap step 199, per-tenant message-send limiting
(AGENTS.md SECTION 9 "Rate Limiting" / "Abuse Prevention" — both
explicitly name "Conversation requests"/"Tenant-specific limits").

Per-client-IP for the auth routes — not per-account, since an
unauthenticated attacker doesn't need a real account to hammer signup/
login, and the email-sending endpoints (magic-link, password-reset)
don't require one either. Fixed window (INCR + EXPIRE-on-first-
increment), not sliding — simple, cheap, and good enough at this
scale; a burst right at a window boundary is an acceptable tradeoff
for not needing a Lua script or sorted-set bookkeeping.

`check_rate_limit` (199) is the same real Redis logic `rate_limit()`'s
own per-IP dependency already used, factored out as a plain callable
once message-send needed a rate-limit KEY that isn't a client IP: a
tenant_id, resolved differently depending on whether the caller is an
authenticated member (`dependencies/tenant.py:get_current_tenant_id`)
or an anonymous visitor (`routers/public_conversation.py`'s own public
Assistant lookup) — two genuinely different resolution paths that
shouldn't be forced into one `Request`-only dependency shape. Each
router builds its own small wrapper around this shared primitive
instead.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request

from config import settings
from errors import TooManyRequestsError
from redis_client import redis_client

# Shared by both routers/conversation.py's own authenticated send/
# regenerate endpoints and routers/public_conversation.py's anonymous
# ones (199) -- they intentionally draw on ONE per-tenant budget keyed
# by tenant_id, not two independent ones, since the real cost being
# protected (an LLM call through orchestrator.handle()) is identical
# either way, and an org's own real limit shouldn't double depending on
# which door a message came through. 60/minute per tenant is generous
# for many real, simultaneous legitimate conversations (roughly one
# message per second sustained) while still capping a scripted flood --
# especially against the anonymous flow, reachable with zero signup
# friction.
MESSAGE_SEND_RATE_LIMIT = 60


async def check_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    # Disabled under pytest: the test suite legitimately calls
    # rate-limited endpoints far more than any real client would, all
    # from the same simulated caller (TestClient's fixed IP, or a
    # handful of tenants reused across many test files), and Redis
    # state persists across test runs (nothing flushes it) — real
    # limits here would make the test suite flaky/order-dependent for
    # reasons that have nothing to do with what's actually being
    # tested. Real enforcement is proven directly by
    # tests/test_rate_limit.py against redis_client itself instead.
    if settings.environment == "test":
        return

    redis_key = f"ratelimit:{key}"
    count = await redis_client.incr(redis_key)
    if count == 1:
        await redis_client.expire(redis_key, window_seconds)

    if count > limit:
        raise TooManyRequestsError("Too many requests. Please try again later.")


def rate_limit(
    *, key_prefix: str, limit: int, window_seconds: int
) -> Callable[[Request], Awaitable[None]]:
    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        await check_rate_limit(
            f"{key_prefix}:{client_ip}", limit=limit, window_seconds=window_seconds
        )

    return dependency
