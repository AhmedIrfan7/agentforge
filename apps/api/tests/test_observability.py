"""Tests for observability.py (roadmap step 256) -- proves the real
OpenTelemetry setup actually produces real spans for real requests
through the real app, not just that setup_tracing() runs without
raising. Attaches a real InMemorySpanExporter to the SAME global
TracerProvider main.py's own module-level setup_tracing() call already
installed (importing `main` triggers that, the same as every other
real integration test in this file) -- OpenTelemetry's global
TracerProvider refuses to be replaced once set (confirmed live: a
second setup_tracing() call just logs a warning), so tests work WITH
that real, already-established provider rather than trying to swap in
an isolated one.
"""

from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from main import app

client = TestClient(app)


def test_setup_tracing_installed_a_real_tracer_provider() -> None:
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)


def test_a_real_http_request_produces_a_real_server_span() -> None:
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    response = client.get("/health")
    assert response.status_code == 200

    server_spans = [
        span
        for span in exporter.get_finished_spans()
        if span.name == "GET /health" and span.kind == trace.SpanKind.SERVER
    ]
    assert len(server_spans) == 1


def test_a_real_db_query_during_a_request_produces_a_real_child_span() -> None:
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # A real login attempt against a nonexistent user still runs a real
    # SELECT against the users table (UserRepository.get_by_email)
    # before failing with 401 -- doesn't need a real account to exist.
    client.post(
        "/auth/login",
        json={"email": "endpoint-test-observability-no-such-user@example.com", "password": "x"},
    )

    finished = exporter.get_finished_spans()
    server_spans = [span for span in finished if span.name == "POST /auth/login"]
    assert len(server_spans) == 1
    request_span_id = server_spans[0].context.span_id

    db_spans = [
        span for span in finished if span.name == "SELECT" and span.kind == trace.SpanKind.CLIENT
    ]
    assert len(db_spans) > 0
    # A real child of the HTTP request's own span, not an unrelated
    # query from a concurrent test -- proves the parent/child
    # relationship this instrumentation is actually FOR, not just that
    # some SELECT span exists somewhere.
    assert any(
        span.parent is not None and span.parent.span_id == request_span_id for span in db_spans
    )
