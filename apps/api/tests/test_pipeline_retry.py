"""Tests for step 112's retry/backoff behavior on dispatch_extraction,
dispatch_embedding_generation, and reindex_chunk_embeddings.

Task.apply() runs a task's real retry loop synchronously and fast --
confirmed live before writing these: eager retries don't actually sleep
in wall-clock time regardless of retry_backoff_max, so this proves the
real retry/give-up behavior (not just that decorator kwargs are present)
without slow tests. Same "no broker/worker needed" reasoning
test_celery_app.py's own ping test already established for .apply().

The underlying coroutine (_run_extraction / _run_embedding_generation /
_reindex_chunk_embeddings) is monkeypatched to fail a controlled number
of times -- each module's own test file already covers its real logic
against real infra; this only needs to prove the retry wiring around it.
"""

import uuid

import pytest

import embeddings_pipeline
import extraction
import vector_maintenance


def test_dispatch_extraction_retries_a_transient_failure_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    async def flaky(document_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return True

    monkeypatch.setattr(extraction, "_run_extraction", flaky)
    monkeypatch.setattr(
        embeddings_pipeline.dispatch_embedding_generation, "delay", lambda *a, **k: None
    )

    result = extraction.dispatch_extraction.apply(args=(str(uuid.uuid4()), str(uuid.uuid4())))
    assert result.successful()
    assert calls["n"] == 3


def test_dispatch_extraction_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def always_fails(document_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        calls["n"] += 1
        raise RuntimeError("permanent")

    monkeypatch.setattr(extraction, "_run_extraction", always_fails)

    result = extraction.dispatch_extraction.apply(args=(str(uuid.uuid4()), str(uuid.uuid4())))
    assert not result.successful()
    assert calls["n"] == 6  # 1 initial attempt + max_retries=5


def test_dispatch_embedding_generation_retries_a_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    async def flaky(document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")

    monkeypatch.setattr(embeddings_pipeline, "_run_embedding_generation", flaky)

    result = embeddings_pipeline.dispatch_embedding_generation.apply(
        args=(str(uuid.uuid4()), str(uuid.uuid4()))
    )
    assert result.successful()
    assert calls["n"] == 2


def test_reindex_task_retries_a_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def flaky() -> None:
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient connection blip")

    monkeypatch.setattr(vector_maintenance, "_reindex_chunk_embeddings", flaky)

    result = vector_maintenance.reindex_chunk_embeddings.apply()
    assert result.successful()
    assert calls["n"] == 2
