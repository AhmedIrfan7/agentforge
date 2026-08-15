"""Tests for memory_observability.py (roadmap step 172). Same
structlog.testing.capture_logs() technique test_agent_tracing.py
already established for asserting real structured log events.
"""

import structlog.testing

from memory_observability import log_memory_event


def test_logs_a_created_event_with_the_real_reason_and_score() -> None:
    with structlog.testing.capture_logs() as logs:
        log_memory_event(
            "created", scope="session", reason="explicit signal phrase", importance_score=0.9
        )

    events = [e for e in logs if e["event"] == "memory_lifecycle"]
    assert len(events) == 1
    assert events[0]["outcome"] == "created"
    assert events[0]["scope"] == "session"
    assert events[0]["reason"] == "explicit signal phrase"
    assert events[0]["importance_score"] == 0.9


def test_logs_an_ignored_event_with_no_importance_score_by_default() -> None:
    with structlog.testing.capture_logs() as logs:
        log_memory_event("ignored", scope="user", reason="too short to be useful")

    events = [e for e in logs if e["event"] == "memory_lifecycle"]
    assert events[0]["outcome"] == "ignored"
    assert events[0]["importance_score"] is None


def test_updated_is_a_real_callable_outcome() -> None:
    """No code path in this codebase calls this with "updated" yet
    (step 173's own job) -- this proves the capability itself is real,
    not that anything uses it today."""
    with structlog.testing.capture_logs() as logs:
        log_memory_event("updated", scope="organization", reason="merged with a newer fact")

    events = [e for e in logs if e["event"] == "memory_lifecycle"]
    assert events[0]["outcome"] == "updated"
