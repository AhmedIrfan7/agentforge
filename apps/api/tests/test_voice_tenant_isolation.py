"""Tenant-isolation tests for voice (roadmap step 230) -- the proof
`test_voice_session_model.py` (219) deliberately deferred here rather
than duplicating. Same two-threat shape `test_retrieval_tenant_
isolation.py` (132) already established: (1) a raw query bypassing
every app-layer filter, proving Postgres RLS alone protects
`voice_sessions`, since `test_tenant_isolation.py` (ADR-0003) never
exercised that table; (2) a realistic attacker who already holds a
REAL, valid credential for their OWN tenant and points it at another
tenant's REAL assistant_id/conversation_id/voice_session_id -- these
ids are never guessed/random, since a random-UUID 404 (already covered
by each endpoint's own existing tests) proves far less than a
genuinely valid target id resolving to nothing.

Covers all three real entry points a cross-tenant attacker could try:
`start_voice_session`/`end_voice_session` (REST, `public_conversation.
py`) and the audio WebSocket's own `_authenticate` (`public_voice.py`).
The websocket case is the strongest of the three: it swaps in another
tenant's real assistant_id AND real voice_session_id while presenting
the attacker's own genuinely valid token, so `VoiceSessionRepository.
get` actually FINDS a real row under the target tenant's context --
only the `voice_session.conversation_id != token_conversation_id`
check (the second, app-layer half of `_authenticate`'s guard) is what
stops it, not RLS returning an empty result outright.

Setup is duplicated from `test_public_voice.py` rather than imported,
matching that file's own stated reasoning: this is Node/test-only
scaffolding, not shared production code.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from db import get_session, set_tenant_context
from main import app
from models.assistant import Assistant
from models.conversation import Conversation
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.session import Session
from models.user import User
from models.voice_session import VoiceSession
from models.workspace import Workspace
from repositories.voice_session import VoiceSessionRepository
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (
            VoiceSession,
            Conversation,
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


def _new_org_workspace_kb_assistant(email: str, *, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Voice Isolation"
    )
    headers = auth_headers(token)
    org_response = client.post(
        "/organizations",
        json={"name": "Voice Isolation Org", "slug": f"voice-isolation-org-{slug}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Voice Isolation WS", "slug": "voice-isolation-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Voice Isolation KB", "slug": "voice-isolation-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Voice Bot", "slug": "voice-isolation-bot", "is_public": True},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    return org_id, assistant_id


def _start_voice_session(assistant_id: uuid.UUID) -> tuple[str, uuid.UUID, uuid.UUID]:
    """Real anonymous conversation + real voice session via the actual
    REST endpoints. Returns (access_token, conversation_id,
    voice_session_id)."""
    conv_response = client.post(f"/public/assistants/{assistant_id}/conversations")
    conv_body = conv_response.json()
    token = conv_body["access_token"]
    conversation_id = uuid.UUID(conv_body["conversation_id"])

    vs_response = client.post(
        f"/public/assistants/{assistant_id}/conversations/{conversation_id}/voice-sessions",
        headers=auth_headers(token),
    )
    voice_session_id = uuid.UUID(vs_response.json()["id"])
    return token, conversation_id, voice_session_id


def _ws_url(assistant_id: uuid.UUID, voice_session_id: uuid.UUID) -> str:
    return f"/public/assistants/{assistant_id}/voice-sessions/{voice_session_id}/audio"


@pytest.mark.anyio
async def test_voice_session_rows_are_invisible_across_tenants_via_rls() -> None:
    org_a, assistant_a = _new_org_workspace_kb_assistant(
        "voice-isolation-rls-a@example.com", slug="rls-a"
    )
    org_b, assistant_b = _new_org_workspace_kb_assistant(
        "voice-isolation-rls-b@example.com", slug="rls-b"
    )
    try:
        _, _, voice_session_b = _start_voice_session(assistant_b)

        async with get_session() as session:
            await set_tenant_context(session, org_b)
            result = await session.execute(
                select(VoiceSession).where(VoiceSession.id == voice_session_b)
            )
            assert result.scalar_one_or_none() is not None

            # Switch to tenant A's context and query the SAME, real
            # voice_session id with no app-layer tenant_id filter of
            # its own -- RLS alone must hide it.
            await set_tenant_context(session, org_a)
            result = await session.execute(
                select(VoiceSession).where(VoiceSession.id == voice_session_b)
            )
            assert result.scalar_one_or_none() is None

            repo = VoiceSessionRepository(session, org_a)
            assert await repo.get(voice_session_b) is None
    finally:
        await _cleanup_org(org_a)
        await _cleanup_org(org_b)
        await _cleanup_user("voice-isolation-rls-a@example.com")
        await _cleanup_user("voice-isolation-rls-b@example.com")


@pytest.mark.anyio
async def test_starting_a_voice_session_with_another_tenants_real_conversation_id_404s() -> None:
    org_a, assistant_a = _new_org_workspace_kb_assistant(
        "voice-isolation-start-a@example.com", slug="start-a"
    )
    org_b, assistant_b = _new_org_workspace_kb_assistant(
        "voice-isolation-start-b@example.com", slug="start-b"
    )
    try:
        conv_response = client.post(f"/public/assistants/{assistant_b}/conversations")
        conv_body = conv_response.json()
        token_b = conv_body["access_token"]
        conversation_b = conv_body["conversation_id"]

        # A real, valid token+conversation for tenant B, pointed at
        # tenant A's real assistant_id in the URL.
        response = client.post(
            f"/public/assistants/{assistant_a}/conversations/{conversation_b}/voice-sessions",
            headers=auth_headers(token_b),
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_a)
        await _cleanup_org(org_b)
        await _cleanup_user("voice-isolation-start-a@example.com")
        await _cleanup_user("voice-isolation-start-b@example.com")


@pytest.mark.anyio
async def test_ending_another_tenants_real_voice_session_404s() -> None:
    org_a, assistant_a = _new_org_workspace_kb_assistant(
        "voice-isolation-end-a@example.com", slug="end-a"
    )
    org_b, assistant_b = _new_org_workspace_kb_assistant(
        "voice-isolation-end-b@example.com", slug="end-b"
    )
    try:
        token_a, conversation_a, _ = _start_voice_session(assistant_a)
        _, _, voice_session_b = _start_voice_session(assistant_b)

        # Tenant A's own real, valid session, attempting to end
        # tenant B's real voice_session_id.
        response = client.post(
            f"/public/assistants/{assistant_a}/conversations/{conversation_a}"
            f"/voice-sessions/{voice_session_b}/end",
            headers=auth_headers(token_a),
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_a)
        await _cleanup_org(org_b)
        await _cleanup_user("voice-isolation-end-a@example.com")
        await _cleanup_user("voice-isolation-end-b@example.com")


@pytest.mark.anyio
async def test_websocket_rejects_another_tenants_real_assistant_and_voice_session() -> None:
    org_a, assistant_a = _new_org_workspace_kb_assistant(
        "voice-isolation-ws-a@example.com", slug="ws-a"
    )
    org_b, assistant_b = _new_org_workspace_kb_assistant(
        "voice-isolation-ws-b@example.com", slug="ws-b"
    )
    try:
        token_a, _, _ = _start_voice_session(assistant_a)
        _, _, voice_session_b = _start_voice_session(assistant_b)

        # Attacker holds their OWN genuinely valid token (tenant A) and
        # points it at tenant B's real assistant_id + real
        # voice_session_id -- VoiceSessionRepository.get actually
        # FINDS a real row under tenant B's context here; only the
        # conversation_id-mismatch check is what must stop this.
        with client.websocket_connect(_ws_url(assistant_b, voice_session_b)) as ws:
            ws.send_json({"token": token_a, "mime_type": "audio/webm"})
            response = ws.receive_json()
            assert response["type"] == "error"
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
    finally:
        await _cleanup_org(org_a)
        await _cleanup_org(org_b)
        await _cleanup_user("voice-isolation-ws-a@example.com")
        await _cleanup_user("voice-isolation-ws-b@example.com")
