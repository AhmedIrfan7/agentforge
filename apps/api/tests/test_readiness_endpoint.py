"""Tests for GET /ready (roadmap step 273) -- proves the readiness probe
does REAL dependency checks, not just returns a static "ok" the way
/health deliberately still does (see main.py's own comment for why
those two need different behavior).
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_ready_reports_ready_when_dependencies_are_real_and_reachable() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": True, "redis": True}


def test_ready_reports_503_when_the_database_is_unreachable() -> None:
    # A real, deliberately-broken get_session() -- proves the endpoint
    # actually calls through to Postgres and reacts to a real failure,
    # not just returning True unconditionally.
    with patch("main.get_session", side_effect=ConnectionError("simulated outage")):
        response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] is False
    # Redis wasn't touched by this failure -- still reports its own real
    # state, not dragged down by an unrelated dependency's outage.
    assert body["checks"]["redis"] is True


def test_ready_reports_503_when_redis_is_unreachable() -> None:
    with patch("main._ping_redis", side_effect=ConnectionError("simulated outage")):
        response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["redis"] is False
    assert body["checks"]["database"] is True
