"""Platform-level system-health dashboard (roadmap step 248) -- queue
depth, worker status, provider status, the exact three things AGENTS.md's
own OBSERVABILITY STACK section names by name ("Worker status," "Queue
health," "Provider status"). Deliberately NOT nested under
/organizations/{id}/... like every other dashboard endpoint this
project has built -- this describes the shared infrastructure serving
every tenant, not any one tenant's own data, so it needs a different
gate than dependencies/rbac.py:require_permission's per-tenant RBAC:
dependencies/auth.py:require_platform_admin, the first real check of
User.is_platform_admin since it was seeded.

Provider status reports configuration presence (is an API key set), not
a live reachability probe. A live probe against llm/openai.py's/llm/
anthropic.py's real endpoints would cost real money on every dashboard
load, and this repo's own CI/local dev never has real provider keys
configured (no OPENAI_API_KEY/ANTHROPIC_API_KEY in any GitHub Actions
secret) -- a live call would always fail here regardless of the
provider's actual health, telling an operator nothing a config check
doesn't already tell them for free. A missing key is genuinely the
single most common real failure mode for one of these integrations.

Worker status runs celery_app.control.inspect().ping() -- a real,
synchronous network round-trip over the broker to whichever workers are
actually listening right now. Queue depth reads the real Redis list
length behind Celery's default queue (confirmed live: kombu's redis
transport stores it as a plain Redis LIST literally named "celery").
Both run together inside one asyncio.to_thread call, using a plain sync
redis-py connection (not redis_client.py's own async singleton) --
that async client is a single connection bound to whichever event loop
first touches it, and Starlette TestClient's internal portal loop
(different from a test's own pytest-anyio loop) made that a real,
observed "Event loop is closed" failure the moment this endpoint's own
tests exercised it through a real HTTP round-trip rather than a direct
function call. A short-lived sync connection has no loop to bind to,
sidestepping the whole class of problem -- and Celery's own control API
is inherently synchronous anyway, so pairing it with a sync Redis call
in the same worker thread is the more natural fit, not a workaround.
"""

import asyncio

import redis as sync_redis
from fastapi import APIRouter, Depends

from celery_app import celery_app
from config import settings
from dependencies.auth import require_platform_admin
from schemas.system_health import ProviderStatusRead, SystemHealthRead

router = APIRouter(prefix="/system-health", tags=["system-health"])

_CELERY_DEFAULT_QUEUE = "celery"
_WORKER_PING_TIMEOUT_SECONDS = 2.0


def _read_queue_and_workers() -> tuple[int, dict[str, object]]:
    sync_client = sync_redis.from_url(settings.redis_url, decode_responses=True)
    try:
        queue_depth = sync_client.llen(_CELERY_DEFAULT_QUEUE)
    finally:
        sync_client.close()
    ping_results = celery_app.control.inspect(timeout=_WORKER_PING_TIMEOUT_SECONDS).ping() or {}
    return queue_depth, ping_results


@router.get("", response_model=SystemHealthRead, dependencies=[Depends(require_platform_admin)])
async def get_system_health() -> SystemHealthRead:
    queue_depth, ping_results = await asyncio.to_thread(_read_queue_and_workers)
    workers = sorted(ping_results.keys())

    providers = [
        ProviderStatusRead(name="openai", configured=bool(settings.openai_api_key)),
        ProviderStatusRead(name="anthropic", configured=bool(settings.anthropic_api_key)),
    ]

    return SystemHealthRead(
        queue_depth=queue_depth,
        worker_count=len(workers),
        workers=workers,
        providers=providers,
    )
