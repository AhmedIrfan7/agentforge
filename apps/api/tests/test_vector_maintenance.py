"""Tests for vector_maintenance.py (roadmap step 110) -- runs a real
REINDEX CONCURRENTLY against the real local Postgres and its real
ix_chunks_embedding_ivfflat index (same "no mocks for infrastructure this
project owns" reasoning test_extraction.py/test_document_endpoints.py
already established), using Task.apply() the same way
test_celery_app.py's own ping test does -- no broker/worker needed to
prove the task body itself is correct.

Deliberately NOT mocked: the one real risk this task carries is a
permission error (REINDEX needs index ownership on Postgres 16, confirmed
live against the least-privilege agentforge_app role before writing
vector_maintenance.py at all -- see its own module docstring), and a
mocked connection would hide exactly that class of failure rather than
catch it.
"""

from celery_app import celery_app
from vector_maintenance import reindex_chunk_embeddings


def test_reindex_task_is_registered() -> None:
    assert "reindex_chunk_embeddings" in celery_app.tasks


def test_reindex_task_runs_successfully_against_real_postgres() -> None:
    # Task.apply() runs the task body in-process (asyncio.run included),
    # no broker/worker needed -- same pattern test_celery_app.py's own
    # ping test uses. This really does run REINDEX INDEX CONCURRENTLY
    # against the real local Postgres and its real
    # ix_chunks_embedding_ivfflat index.
    result = reindex_chunk_embeddings.apply()
    assert result.successful()
