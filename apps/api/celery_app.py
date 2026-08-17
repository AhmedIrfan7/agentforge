"""Celery application (roadmap step 089) -- the worker process's
entrypoint and task registry. `ping` below exists only to prove broker +
worker + result-backend wiring actually works, not as product
functionality -- covered by test_celery_app.py and live-verified
against a real worker process and real Redis, same as every other piece
of infrastructure in this project.

conf.imports lists every other module that defines a @celery_app.task --
extraction.py (step 090), embeddings_pipeline.py (step 108),
vector_maintenance.py (step 110), memory_summarization.py (step 167),
and memory_policy.py (step 168) so far. A worker process only knows
about tasks from modules it has actually imported; `-A celery_app worker`
alone only imports this file, so without this, a task defined in
extraction.py would be invisible to the worker (real KeyError caught
live: 'dispatch_extraction' -- the task existed in the API process,
which does import extraction.py, but not in the separate worker process,
which didn't). Not a direct `from extraction import dispatch_extraction`
here instead, because extraction.py itself imports celery_app from this
module -- conf.imports sidesteps that circular import by deferring the
actual import until Celery's own worker bootstrap, after celery_app
already exists.

Shares config.redis_url with redis_client.py's cache/rate-limiter
connection (see config.py's own docstring: "cache, Celery
broker/backend") -- no operational reason to run a second Redis
deployment at this scale, and Celery's key namespace
("celery-task-meta-*", kombu's queue keys) doesn't collide with
anything else already using this Redis.

task_serializer/result_serializer are explicit "json", not left at
Celery's historical pickle-capable default -- pickle deserializes
arbitrary objects, a real remote-code-execution surface if the broker
is ever misconfigured or compromised, not a default this project should
opt into by omission (AGENTS.md SECTION 9).

Run a worker locally (from apps/api): `uv run celery -A celery_app worker --loglevel=info`.
On Windows, add `--pool=solo` -- Celery's default "prefork" pool needs
os.fork, which Windows doesn't have. CI and production (Linux) don't
need that flag.

As of step 256, setup_tracing() runs here too (this module is every
worker process's own real entrypoint, `-A celery_app worker`, the same
way main.py is the API's) -- a distinct service_name ("agentforge-
worker") from the API's own, so a real trace backend can tell which
process a given span came from. See observability.py's own docstring
for why this is real, unconditional instrumentation that goes nowhere
without a real OTLP endpoint configured.
"""

from celery import Celery

from config import settings
from observability import setup_tracing

setup_tracing(service_name="agentforge-worker")

celery_app = Celery("agentforge", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    imports=(
        "extraction",
        "embeddings_pipeline",
        "vector_maintenance",
        "memory_summarization",
        "memory_policy",
        "message_embedding",
    ),
)


@celery_app.task(name="ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"
