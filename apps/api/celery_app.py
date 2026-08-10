"""Celery application (roadmap step 089) -- the worker process's
entrypoint and task registry. No real tasks yet: step 090 (content
extraction dispatcher) defines the first one. `ping` below exists only
to prove broker + worker + result-backend wiring actually works, not as
product functionality -- covered by test_celery_app.py and live-verified
against a real worker process and real Redis, same as every other piece
of infrastructure in this project.

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
"""

from celery import Celery

from config import settings

celery_app = Celery("agentforge", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"
