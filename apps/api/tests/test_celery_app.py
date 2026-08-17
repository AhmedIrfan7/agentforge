"""Fast, in-process checks for celery_app.py (roadmap step 089) -- config
correctness and the ping task's own logic, using Task.apply() (runs the
task body directly, no broker/worker involved) rather than a real
subprocess worker. A real broker+worker+result-backend round trip is
covered by live verification instead of here, the same reasoning
test_validation.py's module docstring already gives for keeping fast
unit tests separate from slower real-infra integration tests: pytest
running (and tearing down) a worker subprocess on every test run would
buy little regression coverage this step actually needs yet -- nothing
in the app dispatches a real task until step 090 -- while adding real
flakiness risk.
"""

from celery.signals import worker_init
from pytest import MonkeyPatch

from celery_app import celery_app, ping


def test_broker_and_backend_use_the_configured_redis_url() -> None:
    from config import settings

    assert celery_app.conf.broker_url == settings.redis_url
    assert celery_app.conf.result_backend == settings.redis_url


def test_serializers_are_json_not_pickle() -> None:
    # Celery's historical default allows pickle, a real RCE surface if
    # the broker is ever compromised -- must be explicitly ruled out.
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]


def test_ping_task_is_registered() -> None:
    assert "ping" in celery_app.tasks


def test_ping_task_returns_pong() -> None:
    result = ping.apply()
    assert result.successful()
    assert result.result == "pong"


def test_worker_init_starts_the_worker_metrics_server(monkeypatch: MonkeyPatch) -> None:
    # A real socket bind here would collide across pytest-xdist workers
    # all sharing the same configured port (roadmap step 257) -- spying
    # on the call instead proves the real wiring (celery_app.py's own
    # worker_init handler calls metrics.start_worker_metrics_server with
    # the configured port) without needing a real, held-open socket.
    calls: list[int] = []
    monkeypatch.setattr("celery_app.start_worker_metrics_server", calls.append)

    from config import settings

    worker_init.send(sender=None)

    assert calls == [settings.worker_metrics_port]
