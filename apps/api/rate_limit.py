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

As of roadmap step 259 ("Refine rate-limit + abuse-detection
middleware"), also covers two real, previously-uncovered categories
AGENTS.md's own "RATE LIMITING" section names by name: "Document
uploads" (`DOCUMENT_UPLOAD_RATE_LIMIT`, wired into
`routers/document.py:upload_document`) and "Search"
(`SEARCH_RATE_LIMIT`, wired into all four real search endpoints in
`routers/retrieval.py` — dense/keyword/hybrid/context all share ONE
per-tenant budget, the same "one door, one real underlying cost"
reasoning `MESSAGE_SEND_RATE_LIMIT` already established for
message-send, since all four ultimately cost one real embedding call
plus one real DB round trip). Both tenant-keyed, not per-IP — the
resource being protected (storage, embeddings, DB) is shared per
tenant regardless of which member's IP the request came from.

`record_failed_login_attempt` is genuinely distinct from `rate_limit()`
covering "Authentication" above: that caps volume per CLIENT IP
(stops one machine from hammering the endpoint); this tracks failures
per EMAIL (AGENTS.md's own "ABUSE PREVENTION" section names "Repeated
failed logins" as its own bullet, separate from "Credential attacks"),
so it still catches a slow, distributed credential-stuffing attempt
against one specific account from many different IPs, each individually
well under the per-IP cap. It only ever LOGS a distinguishable
structured event once a threshold is crossed (real detection/
visibility, AGENTS.md's own "OBSERVABILITY STACK": "Administrators
should detect problems before users do") — it never itself blocks the
login attempt; `rate_limit(key_prefix="login", ...)` already owns
blocking.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request

from config import settings
from errors import TooManyRequestsError
from logging_config import get_logger
from redis_client import redis_client

logger = get_logger(__name__)

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

# Generous for real bulk-upload workflows (a legitimate onboarding batch
# is dozens of files, not hundreds within a few minutes) while still
# capping a scripted flood against storage/antivirus/extraction, all
# real per-upload costs (steps 084-087).
DOCUMENT_UPLOAD_RATE_LIMIT = 30
DOCUMENT_UPLOAD_RATE_LIMIT_WINDOW_SECONDS = 600

# Search is a normal, high-frequency interactive action (a user refining
# a query, an agent re-querying mid-conversation) — a much higher
# ceiling than message-send's own 60/minute, but still a real ceiling
# against a scripted scrape of a knowledge base's full contents.
SEARCH_RATE_LIMIT = 120
SEARCH_RATE_LIMIT_WINDOW_SECONDS = 60

# How many failed attempts against the SAME email, within the window
# below, before this is treated as a real abuse signal worth a
# distinguishable log line (not just routine per-attempt noise). 15
# minutes is long enough to catch a slow, deliberately-throttled
# credential-stuffing attempt trying to stay under a per-IP rate limit.
FAILED_LOGIN_ABUSE_THRESHOLD = 5
FAILED_LOGIN_ABUSE_WINDOW_SECONDS = 900


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


async def record_failed_login_attempt(email: str) -> None:
    # Same "the test suite legitimately does this far more than any real
    # client would" reasoning as check_rate_limit's own guard above —
    # this function's own regression test calls it directly, bypassing
    # this exact guard the same way tests/test_rate_limit.py already
    # does for check_rate_limit.
    if settings.environment == "test":
        return

    redis_key = f"failed-login-count:{email}"
    count = await redis_client.incr(redis_key)
    if count == 1:
        await redis_client.expire(redis_key, FAILED_LOGIN_ABUSE_WINDOW_SECONDS)

    # Fires exactly once per window, on the attempt that crosses the
    # threshold — not on every attempt after it too, which would just be
    # the same signal repeated as log spam.
    if count == FAILED_LOGIN_ABUSE_THRESHOLD:
        logger.warning("repeated_failed_login_detected", email=email, attempt_count=count)
