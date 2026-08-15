"""Integration tests against the real FastAPI app for
routers/public_conversation.py's new anonymous SSE streaming endpoint
(roadmap step 194). Mirrors test_message_streaming.py's own SSE-parsing
helper and test_public_conversation.py's own org/workspace/kb/public-
assistant setup.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.assistant import Assistant
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.message import Message
from models.organization import Organization
from models.session import Session
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Message, Conversation, Assistant, KnowledgeBase, Workspace):
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
        client, email=email, password="correct horse battery staple", full_name="Public Stream"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Public Stream Org", "slug": f"endpoint-test-pubstream-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Public Stream WS", "slug": "endpoint-test-pubstream-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Public Stream KB", "slug": "endpoint-test-pubstream-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={
            "name": "Public Stream Bot",
            "slug": "endpoint-test-pubstream-bot",
            "is_public": True,
        },
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    return org_id, assistant_id


def _public_url(assistant_id: uuid.UUID, suffix: str = "") -> str:
    return f"/public/assistants/{assistant_id}/conversations{suffix}"


def _parse_sse(body: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for block in body.strip().split("\n\n"):
        if not block:
            continue
        event_line, data_line = block.split("\n", 1)
        events.append((event_line.removeprefix("event: "), data_line.removeprefix("data: ")))
    return events


@pytest.mark.anyio
async def test_anonymous_streaming_delivers_chunks_plus_a_done_event() -> None:
    email = "endpoint-test-pubstream-owner-1@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        create_response = client.post(_public_url(assistant_id))
        conversation_id = create_response.json()["conversation_id"]
        access_token = create_response.json()["access_token"]

        response = client.post(
            _public_url(assistant_id, f"/{conversation_id}/messages/stream"),
            json={"content": "What is your refund policy?"},
            headers=auth_headers(access_token),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(response.text)
        message_events = [e for e in events if e[0] == "message"]
        done_events = [e for e in events if e[0] == "done"]

        assert len(message_events) > 1
        reconstructed = "".join(json.loads(data) for _event, data in message_events)
        assert reconstructed == "No results found."

        assert len(done_events) == 1
        done_payload = json.loads(done_events[0][1])
        assert done_payload["conversation_id"] == conversation_id
        assert done_payload["role"] == "assistant"
        assert done_payload["content"] == "No results found."

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == uuid.UUID(conversation_id))
                .order_by(Message.created_at)
            )
            messages = result.scalars().all()
            assert len(messages) == 2
            assert messages[0].role == "user"
            assert messages[1].role == "assistant"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_anonymous_streaming_with_no_token_401s() -> None:
    email = "endpoint-test-pubstream-owner-2@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email)
    try:
        create_response = client.post(_public_url(assistant_id))
        conversation_id = create_response.json()["conversation_id"]

        response = client.post(
            _public_url(assistant_id, f"/{conversation_id}/messages/stream"),
            json={"content": "hello"},
        )
        assert response.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
