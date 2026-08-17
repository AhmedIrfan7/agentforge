"""Tests for error_tracking.py (roadmap step 258) -- proves real Sentry
capture behavior using a real sentry_sdk.init() with a FakeTransport
swapped in for the duration of each test (sentry_sdk keeps its client as
real, importable process-global state, unlike OpenTelemetry's
TracerProvider, which refuses replacement -- so each test restores the
inert dsn=None state afterward rather than leaving a fake client
bleeding into later tests).

A throwaway FastAPI app wired the SAME way main.py's real one is
(errors.py's own register_exception_handlers, unchanged) is enough to
prove the real mechanism -- no need to break a real production route.
"""

from collections.abc import Iterator

import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.envelope import Envelope
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.transport import Transport

from celery_app import celery_app
from errors import NotFoundError, register_exception_handlers


class _FakeTransport(Transport):
    def __init__(self, captured: list[Envelope]) -> None:
        super().__init__()
        self._captured = captured

    def capture_envelope(self, envelope: Envelope) -> None:
        self._captured.append(envelope)


@pytest.fixture
def captured_envelopes() -> Iterator[list[Envelope]]:
    captured: list[Envelope] = []
    sentry_sdk.init(
        dsn="https://fake@fake.ingest.sentry.io/0",
        transport=_FakeTransport(captured),
        integrations=[StarletteIntegration(), FastApiIntegration(), CeleryIntegration()],
    )
    try:
        yield captured
    finally:
        # Restores the real, inert (transport=None) state main.py's own
        # module-level setup_error_tracking() call already established --
        # otherwise this fake client would leak into every later test in
        # the same pytest-xdist worker process.
        sentry_sdk.init(dsn=None)


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/expected-404")
    def expected_404() -> None:
        raise NotFoundError("nope")

    @app.get("/real-bug")
    def real_bug() -> None:
        raise ValueError("kaboom")

    return app


def test_no_dsn_configured_leaves_the_client_genuinely_inert() -> None:
    # The real, unconfigured state main.py itself boots into in this
    # test environment (no SENTRY_DSN set) -- proves capture calls are
    # real no-ops, not just "no exception observed."
    assert sentry_sdk.get_client().transport is None

    from config import settings

    assert settings.sentry_dsn == ""


def test_an_expected_app_error_is_not_captured(captured_envelopes: list[Envelope]) -> None:
    # NotFoundError has its own specific registered handler
    # (errors.py's own @app.exception_handler(AppError)) -- an expected,
    # client-caused outcome, not an operational failure worth paging on.
    client = TestClient(_build_test_app(), raise_server_exceptions=False)

    response = client.get("/expected-404")

    assert response.status_code == 404
    assert captured_envelopes == []


def test_an_unhandled_exception_is_captured(captured_envelopes: list[Envelope]) -> None:
    # A real, unexpected bug falls through to errors.py's own generic
    # `Exception` handler, which catches it and returns its own clean
    # JSONResponse (never re-raises) -- Sentry's Starlette integration
    # still sees it, hooking the ASGI layer above FastAPI's own
    # exception-handler dispatch rather than the handler's return value.
    client = TestClient(_build_test_app(), raise_server_exceptions=False)

    response = client.get("/real-bug")

    assert response.status_code == 500
    assert len(captured_envelopes) == 1


@celery_app.task(name="test_error_tracking_boom")  # type: ignore[untyped-decorator]
def _boom_task() -> None:
    raise ValueError("kaboom")


def test_a_real_celery_task_failure_is_captured(captured_envelopes: list[Envelope]) -> None:
    # Task.apply() runs the real task body in-process (same pattern as
    # test_celery_app.py) but still fires Celery's real task_failure
    # signal, which is exactly what CeleryIntegration hooks -- no extra
    # signal handler needed in this codebase, unlike metrics.py's own
    # counters, confirmed by this test actually passing.
    result = _boom_task.apply()

    assert result.failed()
    assert len(captured_envelopes) == 1
