"""Integration tests against the real FastAPI app for
routers/system_health.py (roadmap step 248) -- the first real check of
User.is_platform_admin since it was seeded (models/user.py).
"""

import pytest
import redis as sync_redis
from fastapi.testclient import TestClient
from sqlalchemy import select

from config import settings
from db import get_session
from main import app
from models.user import User
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)

_CELERY_DEFAULT_QUEUE = "celery"


async def _make_platform_admin(email: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.is_platform_admin = True
        await session.commit()


def _new_user(email: str) -> str:
    return signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="System Health Test"
    )


@pytest.mark.anyio
async def test_platform_admin_can_read_real_system_health() -> None:
    email = "endpoint-test-system-health-admin@example.com"
    token = _new_user(email)
    await _make_platform_admin(email)

    response = client.get("/system-health", headers=auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["queue_depth"], int)
    assert body["queue_depth"] >= 0
    # No worker process runs during pytest (test_celery_app.py's own
    # docstring already establishes this by design), so this is the one
    # honest value a real inspect().ping() can report here.
    assert body["worker_count"] == 0
    assert body["workers"] == []
    providers = {p["name"]: p["configured"] for p in body["providers"]}
    assert providers == {"openai": False, "anthropic": False}


@pytest.mark.anyio
async def test_non_platform_admin_cannot_read_system_health() -> None:
    email = "endpoint-test-system-health-regular@example.com"
    token = _new_user(email)

    response = client.get("/system-health", headers=auth_headers(token))
    assert response.status_code == 403


@pytest.mark.anyio
async def test_unauthenticated_request_is_rejected() -> None:
    response = client.get("/system-health")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_queue_depth_reflects_a_real_enqueued_task() -> None:
    from celery_app import ping

    email = "endpoint-test-system-health-queue@example.com"
    token = _new_user(email)
    await _make_platform_admin(email)

    before = client.get("/system-health", headers=auth_headers(token)).json()["queue_depth"]
    ping.delay()
    try:
        after_response = client.get("/system-health", headers=auth_headers(token))
        assert after_response.json()["queue_depth"] == before + 1
    finally:
        # No worker consumes this in the test environment -- clean up
        # the real entry this test itself added rather than leaving it
        # for a later run's own baseline to trip over. kombu's redis
        # transport LPUSHes on enqueue (confirmed live: LINDEX 0 held the
        # just-enqueued task's own id), so the entry this test just
        # added is exactly the current head.
        sync_client = sync_redis.from_url(settings.redis_url, decode_responses=True)
        try:
            sync_client.lpop(_CELERY_DEFAULT_QUEUE)
        finally:
            sync_client.close()
