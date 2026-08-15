"""Proves rate_limit() actually enforces limits against real Redis — the
FastAPI-wired version is a no-op under pytest (rate_limit.py's own
docstring explains why), so this calls the dependency function directly
instead of going through an HTTP endpoint.

As of roadmap step 199, also proves the per-tenant message-send
limiters (`routers/conversation.py:rate_limit_message_send`, `routers/
public_conversation.py:rate_limit_public_message_send`) the same way —
called directly, real production-limit enforcement, real Redis.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from starlette.requests import Request

from config import settings
from errors import TooManyRequestsError
from models.assistant import Assistant
from rate_limit import MESSAGE_SEND_RATE_LIMIT, check_rate_limit, rate_limit
from redis_client import redis_client
from routers.conversation import rate_limit_message_send
from routers.public_conversation import rate_limit_public_message_send


def _fake_request(ip: str) -> Request:
    scope = {
        "type": "http",
        "client": (ip, 12345),
        "headers": [],
    }
    return Request(scope)


@pytest.fixture
async def _clean_redis_key() -> AsyncGenerator[str]:
    key_prefix = "test-rate-limit-direct"
    yield key_prefix
    async for key in redis_client.scan_iter(match=f"ratelimit:{key_prefix}:*"):
        await redis_client.delete(key)


@pytest.fixture(autouse=True)
async def _disconnect_redis_after_test() -> AsyncGenerator[None]:
    """redis_client (redis_client.py) is a module-level singleton whose
    connection pool binds to whichever event loop first used it — same
    class of issue db.py's SQLAlchemy engine had under pytest (see
    db.py's NullPool comment). Closing it here, within this same test's
    still-active loop, before that loop tears down, stops the connection
    from surviving (stale) into a later test's different loop. Kept
    local to this file rather than conftest.py: every test function here
    is already async (@pytest.mark.anyio), so there's no risk of the
    async-autouse-fixture-with-sync-tests pytest bug this project hit
    earlier when such a fixture was added file-wide elsewhere — that
    fix doesn't generalize to conftest.py where sync tests do exist.
    """
    yield
    await redis_client.aclose()


@pytest.mark.anyio
async def test_rate_limit_allows_up_to_the_limit_then_blocks(_clean_redis_key: str) -> None:
    key_prefix = _clean_redis_key
    limiter = rate_limit(key_prefix=key_prefix, limit=3, window_seconds=60)
    request = _fake_request("203.0.113.1")

    # Bypass the test-environment no-op deliberately, to prove the real
    # enforcement logic works — see rate_limit.py's docstring.
    with patch.object(settings, "environment", "production"):
        await limiter(request)
        await limiter(request)
        await limiter(request)
        with pytest.raises(TooManyRequestsError):
            await limiter(request)


@pytest.mark.anyio
async def test_rate_limit_is_isolated_per_ip(_clean_redis_key: str) -> None:
    key_prefix = _clean_redis_key
    limiter = rate_limit(key_prefix=key_prefix, limit=1, window_seconds=60)
    request_a = _fake_request("203.0.113.10")
    request_b = _fake_request("203.0.113.20")

    with patch.object(settings, "environment", "production"):
        await limiter(request_a)
        with pytest.raises(TooManyRequestsError):
            await limiter(request_a)

        # Different IP, same limiter — must not be blocked by A's usage.
        await limiter(request_b)


@pytest.mark.anyio
async def test_rate_limit_is_a_noop_under_test_environment(_clean_redis_key: str) -> None:
    key_prefix = _clean_redis_key
    limiter = rate_limit(key_prefix=key_prefix, limit=1, window_seconds=60)
    request = _fake_request("203.0.113.30")

    # No patch here — settings.environment is genuinely "test" (see
    # tests/conftest.py), so this must never raise no matter how many
    # times it's called.
    for _ in range(5):
        await limiter(request)


@pytest.mark.anyio
async def test_check_rate_limit_allows_up_to_the_limit_then_blocks(_clean_redis_key: str) -> None:
    key = f"{_clean_redis_key}:direct"

    with patch.object(settings, "environment", "production"):
        await check_rate_limit(key, limit=3, window_seconds=60)
        await check_rate_limit(key, limit=3, window_seconds=60)
        await check_rate_limit(key, limit=3, window_seconds=60)
        with pytest.raises(TooManyRequestsError):
            await check_rate_limit(key, limit=3, window_seconds=60)


@pytest.fixture
async def _clean_tenant_keys() -> AsyncGenerator[list[uuid.UUID]]:
    tenant_ids: list[uuid.UUID] = []
    yield tenant_ids
    for tenant_id in tenant_ids:
        await redis_client.delete(f"ratelimit:message_send:{tenant_id}")


@pytest.mark.anyio
async def test_message_send_rate_limit_is_isolated_per_tenant(
    _clean_tenant_keys: list[uuid.UUID],
) -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    _clean_tenant_keys.extend([tenant_a, tenant_b])

    with patch.object(settings, "environment", "production"):
        for _ in range(MESSAGE_SEND_RATE_LIMIT):
            await rate_limit_message_send(tenant_id=tenant_a)
        with pytest.raises(TooManyRequestsError):
            await rate_limit_message_send(tenant_id=tenant_a)

        # Different tenant, same limiter — must not be blocked by
        # tenant_a's usage.
        await rate_limit_message_send(tenant_id=tenant_b)


@pytest.mark.anyio
async def test_message_send_rate_limit_is_shared_across_authenticated_and_anonymous_callers(
    _clean_tenant_keys: list[uuid.UUID],
) -> None:
    """routers/conversation.py:rate_limit_message_send (authenticated)
    and routers/public_conversation.py:rate_limit_public_message_send
    (anonymous) are keyed by the identical `message_send:{tenant_id}`
    prefix (rate_limit.py's own MESSAGE_SEND_RATE_LIMIT docstring
    explains why) — proves they really draw from ONE shared per-tenant
    budget, not two independent ones."""
    tenant_id = uuid.uuid4()
    _clean_tenant_keys.append(tenant_id)
    assistant = Assistant(tenant_id=tenant_id)

    with patch.object(settings, "environment", "production"):
        for _ in range(MESSAGE_SEND_RATE_LIMIT):
            await rate_limit_message_send(tenant_id=tenant_id)

        # Budget already exhausted by the "authenticated" calls above —
        # the anonymous door for the SAME tenant hits the same wall
        # immediately, with no separate allowance of its own.
        with pytest.raises(TooManyRequestsError):
            await rate_limit_public_message_send(assistant=assistant)
