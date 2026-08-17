"""Prometheus-compatible metrics export (roadmap step 257, AGENTS.md's
own "OBSERVABILITY"/"OBSERVABILITY STACK" sections: "Metrics"). A real
GET /metrics endpoint in the standard Prometheus text exposition format
(prometheus_client.generate_latest()) -- unauthenticated, matching
universal Prometheus scraping convention (a Prometheus server has no
JWT to present; access control for this endpoint is a real
deployment's own network-level concern -- a firewall/VPC boundary --
not this app's job, the same "auth is a different layer's job"
reasoning /health already established).

Scoped to what's cheap enough to update in-process on every real event
(HTTP requests, Celery task executions) -- deliberately NOT
re-exposing routers/system_health.py's own queue-depth/worker-count
checks here, even though AGENTS.md's own OBSERVABILITY STACK section
names both: those need a real ~1-2s Celery control.inspect() round
trip, and Prometheus scrapes /metrics every 15-30s expecting a fast,
in-memory response -- baking a slow network call into every scrape
would be a real, avoidable performance foot-gun for a widely-scraped
endpoint. That data is already real and available at /system-health
for the cases that actually need it, not duplicated here.

http_requests_total / http_request_duration_seconds are labeled by the
real ROUTE PATTERN (e.g. "/organizations/{organization_id}/workspaces"),
never the resolved path with real UUIDs in it -- an unbounded set of
label values (one per real organization/workspace/etc. ID ever
requested) would make this endpoint's own output grow without bound,
defeating the point of a metrics endpoint. celery_task_total/celery_
task_duration_seconds hook Celery's own real task_prerun/task_postrun/
task_failure signals -- real per-task-name, per-status counts, not a
sampled or estimated approximation.

TWO SEPARATE PROCESSES, TWO SEPARATE SCRAPE TARGETS: prometheus_client's
default registry lives in-process, and a real Celery task dispatched via
`.delay()` runs in the worker process (celery_app.py's own `-A celery_app
worker` entrypoint), not the API process -- confirmed live, dispatching a
task from a separate process never moved the API's own /metrics counters.
The worker process has no web server of its own to expose GET /metrics
on, so it can't reuse the FastAPI route below; instead
start_worker_metrics_server() (called once from celery_app.py's own
worker_init signal handler, not on every import) opens a small dedicated
prometheus_client HTTP server on settings.worker_metrics_port -- the
standard prometheus_client pattern for a non-web background process.
A real deployment scrapes both targets (the API's own port + this one)
as separate Prometheus jobs.
"""

import time
from typing import Any

from celery.signals import task_failure, task_postrun, task_prerun
from fastapi import FastAPI, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
    start_http_server,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the API.",
    ["method", "path", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)

celery_task_total = Counter(
    "celery_task_total",
    "Total Celery tasks executed, by task name and outcome.",
    ["task_name", "status"],
)
celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task execution duration in seconds.",
    ["task_name"],
)

_task_start_times: dict[str, float] = {}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        # request.scope["route"] is only set once Starlette's router has
        # actually matched a route -- populated by the time call_next()
        # returns (routing happens inside that call), so this is the
        # real route PATTERN, not the resolved path. A request that
        # matched no route at all (a genuine 404) has no route object;
        # "unmatched" keeps that case's own label bounded too.
        route = request.scope.get("route")
        path = route.path if route is not None else "unmatched"

        http_requests_total.labels(
            method=request.method, path=path, status=str(response.status_code)
        ).inc()
        http_request_duration_seconds.labels(method=request.method, path=path).observe(duration)
        return response


def register_metrics_middleware(app: FastAPI) -> None:
    app.add_middleware(MetricsMiddleware)


@task_prerun.connect  # type: ignore[untyped-decorator]
def _on_task_prerun(task_id: str, **kwargs: Any) -> None:
    _task_start_times[task_id] = time.perf_counter()


@task_postrun.connect  # type: ignore[untyped-decorator]
def _on_task_postrun(task_id: str, task: Any, state: str, **kwargs: Any) -> None:
    start = _task_start_times.pop(task_id, None)
    task_name = getattr(task, "name", "unknown")
    # "FAILURE" here means the task raised and Celery gave up retrying --
    # task_failure below fires for that same real event too, but reports
    # it under _on_task_failure instead, so this branch only counts the
    # real, distinct outcomes task_failure doesn't already cover.
    if state != "FAILURE":
        celery_task_total.labels(task_name=task_name, status=state.lower()).inc()
    if start is not None:
        celery_task_duration_seconds.labels(task_name=task_name).observe(
            time.perf_counter() - start
        )


@task_failure.connect  # type: ignore[untyped-decorator]
def _on_task_failure(task_id: str, sender: Any, **kwargs: Any) -> None:
    _task_start_times.pop(task_id, None)
    task_name = getattr(sender, "name", "unknown")
    celery_task_total.labels(task_name=task_name, status="failure").inc()


def render_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def start_worker_metrics_server(port: int) -> None:
    start_http_server(port)
