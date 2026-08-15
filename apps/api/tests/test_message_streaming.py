"""Integration tests against the real FastAPI app for
routers/conversation.py's SSE streaming endpoint (roadmap step 180).
Duplicates test_message_endpoints.py's own small setup helpers rather
than importing them, matching this project's "duplicate small helpers
per test file, never cross-import" convention (established step 156).
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
from models.membership import Membership
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
        for model in (Message, Conversation, Assistant, KnowledgeBase, Workspace, Membership):
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


def _new_org_workspace_kb_assistant_conversation(
    email: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Stream Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Streaming Test Org", "slug": f"endpoint-test-stream-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Stream Test Workspace", "slug": "endpoint-test-stream-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Stream Test KB", "slug": "endpoint-test-stream-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Stream Bot", "slug": "endpoint-test-stream-bot"},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    conv_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}/conversations",
        headers=headers,
    )
    conversation_id = uuid.UUID(conv_response.json()["id"])
    return org_id, workspace_id, kb_id, assistant_id, conversation_id, headers


def _stream_url(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
        f"/conversations/{conversation_id}/messages/stream"
    )


def _parse_sse(body: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for block in body.strip().split("\n\n"):
        if not block:
            continue
        event_line, data_line = block.split("\n", 1)
        events.append((event_line.removeprefix("event: "), data_line.removeprefix("data: ")))
    return events


def test_streaming_route_requires_auth() -> None:
    response = client.post(
        _stream_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()),
        json={"content": "hello"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_streaming_delivers_the_response_as_multiple_sse_chunks_plus_a_done_event() -> None:
    email = "endpoint-test-stream-owner-1@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        response = client.post(
            _stream_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "What is your refund policy?"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(response.text)
        message_events = [e for e in events if e[0] == "message"]
        done_events = [e for e in events if e[0] == "done"]

        # "No results found." (no documents in this KB) splits into
        # multiple word-level chunks, not one single blob -- proves
        # real incremental chunking happened, not a single write
        # dressed up as SSE.
        assert len(message_events) > 1
        reconstructed = "".join(json.loads(data) for _event, data in message_events)
        assert reconstructed == "No results found."

        assert len(done_events) == 1
        done_payload = json.loads(done_events[0][1])
        assert done_payload["conversation_id"] == str(conversation_id)
        assert done_payload["role"] == "assistant"
        assert done_payload["content"] == "No results found."

        # The stream persisted real Message rows, same as the
        # non-streaming endpoint -- streaming only changes delivery.
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
            messages = result.scalars().all()
            assert len(messages) == 2
            assert messages[0].role == "user"
            assert messages[1].role == "assistant"
            assert messages[1].content == "No results found."
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_streaming_to_another_users_conversation_is_not_reachable() -> None:
    email = "endpoint-test-stream-owner-2@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, _owner_headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    outsider_email = "endpoint-test-stream-outsider@example.com"
    try:
        outsider_token = signup_and_login(
            client,
            email=outsider_email,
            password="correct horse battery staple",
            full_name="Outsider",
        )
        response = client.post(
            _stream_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "Trying to butt in."},
            headers=auth_headers(outsider_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
        await _cleanup_user(outsider_email)
