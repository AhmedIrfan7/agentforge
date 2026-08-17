"""OpenTelemetry distributed tracing setup (roadmap step 256, AGENTS.md's
own "OBSERVABILITY" section: "Distributed tracing"). Instruments the
real request/task path across both halves the roadmap step's own
wording names -- the API process (FastAPI) and Celery workers
(celery_app.py, step 089) -- plus SQLAlchemy, since a span for "how
long did this HTTP request take" is far less useful without its own
real child spans for the DB queries that made up most of that time.

No real OTLP collector (Jaeger, Honeycomb, Datadog, etc.) is configured
anywhere in this project -- the same honest state as openai_api_key/
anthropic_api_key (config.py, ADR-0004): real, tested instrumentation
code, genuinely inert until a real endpoint is configured.
OTEL_EXPORTER_OTLP_ENDPOINT (config.py) controls this: set, spans
export there for real over OTLP/HTTP; empty (every environment this
project runs in today), spans still get created for real (the
instrumentation itself is unconditional -- FastAPI/SQLAlchemy/Celery
are always instrumented, matching how every other real-but-unconfigured
integration in this codebase behaves) but go nowhere in test/production,
except in development, where they print to stdout so a local developer
gets real, immediate trace visibility without standing up a collector
first.

Distinct from agents/tracing.py, which is this codebase's OWN
purpose-built per-agent execution log (a real Postgres row per agent
run, feeding analytics/agent.py's own dashboard) -- a genuinely
different concern from an industry-standard distributed-tracing
protocol meant for an external observability backend. Neither replaces
the other; a future step could correlate them via a shared trace_id if
a real need for that ever shows up, but nothing here does that
speculatively.
"""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from config import settings


def setup_tracing(*, service_name: str) -> None:
    """Called once per process -- main.py for the API, celery_app.py for
    workers, each with its own service_name so a real trace backend can
    tell API spans from worker spans apart. Idempotent in practice:
    BaseInstrumentor.instrument() and trace.set_tracer_provider() both
    already no-op (with a warning, not an exception) if called twice,
    which matters here because pytest imports both main.py and
    celery_app.py into the same process."""
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    if settings.otel_exporter_otlp_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )
    elif settings.is_development:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    # Else: a real TracerProvider with no span processor attached --
    # spans are still created (negligible cost), just never exported
    # anywhere. Test/production with no real endpoint configured stays
    # exactly this honest, inert state.

    trace.set_tracer_provider(provider)

    # Imported here, not at module level -- db.py's own module-level
    # `engine`/`worker_engine` must already exist as real objects before
    # SQLAlchemyInstrumentor can attach event listeners to them.
    # SQLAlchemyInstrumentor().instrument() with NO engine/engines kwarg
    # only monkey-patches the create_engine/create_async_engine
    # FUNCTIONS themselves (confirmed live: calling it that way produced
    # zero DB spans for this app's real requests) -- it only catches
    # engines created AFTER instrument() runs, which db.py's own
    # module-level engines never are, regardless of import order.
    # Passing the real, already-created engines directly attaches real
    # event listeners to them specifically, sidestepping the whole
    # import-order problem. `.sync_engine`, not the AsyncEngine itself
    # -- confirmed live, SQLAlchemy raises NotImplementedError
    # ("asynchronous events are not implemented... apply synchronous
    # listeners to the AsyncEngine.sync_engine") if you try the async
    # wrapper directly; the real events (before/after_cursor_execute
    # etc.) still fire correctly on the sync core underneath asyncpg.
    from db import engine, worker_engine

    SQLAlchemyInstrumentor().instrument(engines=[engine.sync_engine, worker_engine.sync_engine])
    # opentelemetry-instrumentation-celery is still a beta package
    # (0.65b0) -- CeleryInstrumentor's own __init__ ships with no type
    # annotations, tripping strict mode's disallow-untyped-calls even
    # though the module itself resolves and works correctly at runtime.
    CeleryInstrumentor().instrument()  # type: ignore[no-untyped-call]


def instrument_fastapi_app(app: FastAPI) -> None:
    # Separate from setup_tracing() above: this needs the real `app`
    # instance, which doesn't exist yet at that function's own call site
    # (main.py calls setup_tracing() before constructing `app`, so
    # instrumentation covers every route registered afterward too).
    FastAPIInstrumentor.instrument_app(app)
