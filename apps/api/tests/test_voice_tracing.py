"""Tests for voice/tracing.py (roadmap step 227). Same
structlog.testing.capture_logs() technique test_agent_tracing.py
already established at step 153 for asserting real structured log
events.
"""

import uuid
from collections.abc import MutableMapping
from typing import Any

import structlog.testing

from voice.tracing import (
    VoiceSynthesisTrace,
    VoiceTurnProcessingTrace,
    log_synthesis,
    log_turn_processing,
)


def _events(logs: list[MutableMapping[str, Any]], name: str) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == name]


def test_log_turn_processing_emits_a_real_structured_event() -> None:
    voice_session_id = uuid.uuid4()
    with structlog.testing.capture_logs() as logs:
        log_turn_processing(
            VoiceTurnProcessingTrace(
                voice_session_id=voice_session_id,
                status="success",
                stt_latency_ms=123.456,
                reply_latency_ms=789.012,
                total_latency_ms=912.468,
            )
        )

    events = _events(logs, "voice_turn_processing")
    assert len(events) == 1
    assert events[0]["voice_session_id"] == str(voice_session_id)
    assert events[0]["status"] == "success"
    assert events[0]["stt_latency_ms"] == 123.46
    assert events[0]["reply_latency_ms"] == 789.01
    assert events[0]["total_latency_ms"] == 912.47


def test_log_turn_processing_handles_a_real_none_reply_latency() -> None:
    # A real, honest state: an empty/near-silent transcript or a real
    # STT failure never reaches reply generation at all.
    voice_session_id = uuid.uuid4()
    with structlog.testing.capture_logs() as logs:
        log_turn_processing(
            VoiceTurnProcessingTrace(
                voice_session_id=voice_session_id,
                status="success",
                stt_latency_ms=50.0,
                reply_latency_ms=None,
                total_latency_ms=50.0,
            )
        )

    events = _events(logs, "voice_turn_processing")
    assert events[0]["reply_latency_ms"] is None


def test_log_turn_processing_reports_a_real_failure_status() -> None:
    voice_session_id = uuid.uuid4()
    with structlog.testing.capture_logs() as logs:
        log_turn_processing(
            VoiceTurnProcessingTrace(
                voice_session_id=voice_session_id,
                status="failure",
                stt_latency_ms=20.0,
                reply_latency_ms=None,
                total_latency_ms=20.0,
            )
        )

    events = _events(logs, "voice_turn_processing")
    assert events[0]["status"] == "failure"


def test_log_synthesis_emits_a_real_structured_event() -> None:
    voice_session_id = uuid.uuid4()
    with structlog.testing.capture_logs() as logs:
        log_synthesis(
            VoiceSynthesisTrace(
                voice_session_id=voice_session_id, status="success", tts_latency_ms=456.789
            )
        )

    events = _events(logs, "voice_synthesis")
    assert len(events) == 1
    assert events[0]["voice_session_id"] == str(voice_session_id)
    assert events[0]["status"] == "success"
    assert events[0]["tts_latency_ms"] == 456.79


def test_log_synthesis_reports_a_real_interrupted_status() -> None:
    # A distinct third outcome from success/failure -- a real barge-in
    # (225) cancels an in-flight synthesis; conflating that with a slow
    # or failed provider call would make latency numbers meaningless.
    voice_session_id = uuid.uuid4()
    with structlog.testing.capture_logs() as logs:
        log_synthesis(
            VoiceSynthesisTrace(
                voice_session_id=voice_session_id, status="interrupted", tts_latency_ms=42.0
            )
        )

    events = _events(logs, "voice_synthesis")
    assert events[0]["status"] == "interrupted"
