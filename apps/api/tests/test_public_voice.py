"""Integration tests for the streaming audio ingestion WebSocket
(roadmap step 221). Same real org/workspace/kb/public-assistant setup
`test_public_conversation.py` already established, plus a real
anonymous conversation + voice session started through the actual REST
endpoints (192, 220) -- nothing here is mocked except
`WhisperSTTProvider.transcribe` itself for the success-path tests,
since re-proving Whisper's own request/response handling is already
`test_whisper_stt_provider.py`'s job; this file is about proving the
WebSocket endpoint's own auth/protocol/buffering logic, not the STT
provider's.
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

import routers.public_voice as public_voice_module
from db import get_session, set_tenant_context
from main import app
from models.assistant import Assistant
from models.chunk import Chunk
from models.conversation import Conversation
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.message import Message
from models.organization import Organization
from models.session import Session
from models.user import User
from models.voice_session import VoiceSession
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login
from voice.base import TranscriptionResult

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (
            VoiceSession,
            Message,
            Conversation,
            Chunk,
            Document,
            Assistant,
            KnowledgeBase,
            Workspace,
        ):
            result = await session.execute(select(model).where(model.tenant_id == org_id))
            for row in result.scalars().all():
                await session.delete(row)
            await session.flush()
        org = await session.get(Organization, org_id)
        if org is not None:
            await session.delete(org)
        await session.commit()


async def _cleanup_user(email: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            return
        session_result = await session.execute(select(Session).where(Session.user_id == user.id))
        for s in session_result.scalars().all():
            await session.delete(s)
        await session.delete(user)
        await session.commit()


def _new_org_workspace_kb_assistant(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Voice Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Voice Test Org", "slug": f"endpoint-test-voice-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Voice Test WS", "slug": "endpoint-test-voice-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Voice Test KB", "slug": "endpoint-test-voice-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Voice Bot", "slug": "endpoint-test-voice-bot", "is_public": True},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    return org_id, assistant_id


def _start_voice_session(assistant_id: uuid.UUID) -> tuple[str, uuid.UUID, str]:
    """Real anonymous conversation + real voice session via the actual
    REST endpoints. Returns (anonymous_token, voice_session_id,
    conversation_id)."""
    conv_response = client.post(f"/public/assistants/{assistant_id}/conversations")
    conv_body = conv_response.json()
    token = conv_body["access_token"]
    conversation_id = conv_body["conversation_id"]

    vs_response = client.post(
        f"/public/assistants/{assistant_id}/conversations/{conversation_id}/voice-sessions",
        headers=auth_headers(token),
    )
    voice_session_id = uuid.UUID(vs_response.json()["id"])
    return token, voice_session_id, conversation_id


def _ws_url(assistant_id: uuid.UUID, voice_session_id: uuid.UUID) -> str:
    return f"/public/assistants/{assistant_id}/voice-sessions/{voice_session_id}/audio"


@pytest.mark.anyio
async def test_missing_token_or_mime_type_is_rejected() -> None:
    email = "endpoint-test-voice-owner-1@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        _, voice_session_id, _ = _start_voice_session(assistant_id)
        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({})
            response = ws.receive_json()
            assert response["type"] == "error"
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_an_invalid_token_is_rejected() -> None:
    email = "endpoint-test-voice-owner-2@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        _, voice_session_id, _ = _start_voice_session(assistant_id)
        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({"token": "garbage", "mime_type": "audio/webm"})
            response = ws.receive_json()
            assert response["type"] == "error"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_a_token_for_a_different_conversation_is_rejected() -> None:
    email = "endpoint-test-voice-owner-3@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        _, first_voice_session_id, _ = _start_voice_session(assistant_id)
        second_token, _, _ = _start_voice_session(assistant_id)

        with client.websocket_connect(_ws_url(assistant_id, first_voice_session_id)) as ws:
            ws.send_json({"token": second_token, "mime_type": "audio/webm"})
            response = ws.receive_json()
            assert response["type"] == "error"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_an_ended_voice_session_is_rejected() -> None:
    email = "endpoint-test-voice-owner-4@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        token, voice_session_id, _ = _start_voice_session(assistant_id)

        # No session-end endpoint exists yet (step 228) -- mark it ended
        # directly, the same way model tests exercise a field with no
        # real setter endpoint yet.
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            voice_session = await session.get(VoiceSession, voice_session_id)
            assert voice_session is not None
            voice_session.ended_at = datetime.now(UTC)
            await session.commit()

        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({"token": token, "mime_type": "audio/webm"})
            response = ws.receive_json()
            assert response["type"] == "error"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_valid_credentials_receive_a_ready_message() -> None:
    email = "endpoint-test-voice-owner-5@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        token, voice_session_id, _ = _start_voice_session(assistant_id)
        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({"token": token, "mime_type": "audio/webm"})
            response = ws.receive_json()
            assert response["type"] == "ready"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_turn_with_no_buffered_audio_returns_an_error() -> None:
    email = "endpoint-test-voice-owner-6@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        token, voice_session_id, _ = _start_voice_session(assistant_id)
        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({"token": token, "mime_type": "audio/webm"})
            ws.receive_json()  # ready

            ws.send_text(json.dumps({"type": "end_turn"}))
            response = ws.receive_json()
            assert response["type"] == "error"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_streaming_audio_then_end_turn_returns_a_real_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_transcribe(
        self: object, audio: bytes, *, mime_type: str
    ) -> TranscriptionResult:
        assert audio == b"fake-audio-chunk-1fake-audio-chunk-2"
        assert mime_type == "audio/webm"
        return TranscriptionResult(text="what is your refund policy", language="english")

    monkeypatch.setattr(type(public_voice_module._stt_provider), "transcribe", _fake_transcribe)

    email = "endpoint-test-voice-owner-7@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        token, voice_session_id, _ = _start_voice_session(assistant_id)
        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({"token": token, "mime_type": "audio/webm"})
            ws.receive_json()  # ready

            ws.send_bytes(b"fake-audio-chunk-1")
            ws.send_bytes(b"fake-audio-chunk-2")
            ws.send_text(json.dumps({"type": "end_turn"}))

            response = ws.receive_json()
            assert response == {
                "type": "transcript",
                "text": "what is your refund policy",
                "language": "english",
            }
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_a_second_turn_on_the_same_connection_works_after_the_buffer_resets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bytes] = []

    async def _fake_transcribe(
        self: object, audio: bytes, *, mime_type: str
    ) -> TranscriptionResult:
        calls.append(audio)
        return TranscriptionResult(text=f"turn {len(calls)}", language="english")

    monkeypatch.setattr(type(public_voice_module._stt_provider), "transcribe", _fake_transcribe)

    email = "endpoint-test-voice-owner-8@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        token, voice_session_id, _ = _start_voice_session(assistant_id)
        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({"token": token, "mime_type": "audio/webm"})
            ws.receive_json()  # ready

            ws.send_bytes(b"turn-one-audio")
            ws.send_text(json.dumps({"type": "end_turn"}))
            first = ws.receive_json()

            ws.send_bytes(b"turn-two-audio")
            ws.send_text(json.dumps({"type": "end_turn"}))
            second = ws.receive_json()

            assert first["text"] == "turn 1"
            assert second["text"] == "turn 2"
            assert calls == [b"turn-one-audio", b"turn-two-audio"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_a_real_transcription_failure_is_reported_as_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unlike the tests above, this exercises the REAL
    WhisperSTTProvider against the real api.openai.com endpoint with no
    API key configured in this environment -- the same honest,
    fail-closed behavior test_whisper_stt_provider.py's own live probe
    already documented, now proven through this endpoint end to end."""
    email = "endpoint-test-voice-owner-9@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        token, voice_session_id, _ = _start_voice_session(assistant_id)
        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({"token": token, "mime_type": "audio/webm"})
            ws.receive_json()  # ready

            ws.send_bytes(b"real-audio-bytes")
            ws.send_text(json.dumps({"type": "end_turn"}))
            response = ws.receive_json()
            assert response["type"] == "error"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_exceeding_the_max_buffer_size_closes_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(public_voice_module, "MAX_AUDIO_BUFFER_BYTES", 10)

    email = "endpoint-test-voice-owner-10@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        token, voice_session_id, _ = _start_voice_session(assistant_id)
        with client.websocket_connect(_ws_url(assistant_id, voice_session_id)) as ws:
            ws.send_json({"token": token, "mime_type": "audio/webm"})
            ws.receive_json()  # ready

            ws.send_bytes(b"this is definitely more than ten bytes")
            response = ws.receive_json()
            assert response["type"] == "error"
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
