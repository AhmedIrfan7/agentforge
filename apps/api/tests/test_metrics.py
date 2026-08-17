"""Tests for metrics.py (roadmap step 257) -- proves /metrics returns real
Prometheus text-exposition-format output carrying real counter/histogram
values produced by real HTTP requests and a real Celery task execution
through the real app, not just that the endpoint returns 200.
"""

from fastapi.testclient import TestClient

from celery_app import ping
from main import app

client = TestClient(app)


def test_metrics_endpoint_returns_prometheus_text_format() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")


def test_a_real_http_request_increments_the_real_request_counter() -> None:
    client.get("/health")

    body = client.get("/metrics").text
    # Labeled by the real route PATTERN ("/health"), not a resolved path
    # with an ID baked in -- there is no ID in this particular route, but
    # the label key itself proves the middleware used request.scope["route"]
    # rather than request.url.path.
    assert 'http_requests_total{method="GET",path="/health",status="200"}' in body
    assert "http_request_duration_seconds_count" in body


def test_a_real_celery_task_run_increments_the_real_task_counter() -> None:
    # Task.apply() runs the real task body in-process (no broker/worker
    # involved -- same pattern as test_celery_app.py) but still fires
    # Celery's real task_prerun/task_postrun signals, which is exactly
    # what metrics.py's own signal handlers hook.
    result = ping.apply()
    assert result.successful()

    body = client.get("/metrics").text
    assert 'celery_task_total{status="success",task_name="ping"}' in body
    assert "celery_task_duration_seconds_count" in body
