"""Integration tests for the follow-up-questions endpoint (roadmap
step 190). Mirrors test_conversation_search_endpoints.py's own
approach (183) for a real-LLM-backed endpoint: mock the provider's own
HTTP transport for the success/wiring path, confirm the real "no
OPENAI_API_KEY" 500 via live verification rather than a formal pytest
endpoint test (a real network call in the automated suite would be
slow/flaky) -- the module-level test (test_follow_up_questions.py)
already proves that failure mode directly against the real API.
"""

import uuid

import httpx
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


def _client_factory(handler: httpx.MockTransport) -> type[httpx.AsyncClient]:
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = handler
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    return _PatchedClient


def _mock_completion_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


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
        client, email=email, password="correct horse battery staple", full_name="FollowUp Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "FollowUp Test Org", "slug": f"endpoint-test-followup-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "FollowUp Test WS", "slug": "endpoint-test-followup-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "FollowUp Test KB", "slug": "endpoint-test-followup-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "FollowUp Bot", "slug": "endpoint-test-followup-bot"},
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


def _follow_up_url(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID | str,
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
        f"/conversations/{conversation_id}/messages/{message_id}/follow-up-questions"
    )


def _send_message(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    headers: dict[str, str],
) -> str:
    response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is your refund policy?"},
        headers=headers,
    )
    message_id: str = response.json()["id"]
    return message_id


@pytest.mark.anyio
async def test_generates_real_follow_up_questions_through_the_real_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _mock_completion_response("1. What about exchanges?\n2. Any restocking fee?")

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )

    email = "endpoint-test-followup-owner-1@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        message_id = _send_message(
            org_id, workspace_id, kb_id, assistant_id, conversation_id, headers
        )
        response = client.post(
            _follow_up_url(org_id, workspace_id, kb_id, assistant_id, conversation_id, message_id),
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["questions"] == [
            "What about exchanges?",
            "Any restocking fee?",
        ]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_follow_up_questions_on_a_user_message_404s() -> None:
    email = "endpoint-test-followup-owner-2@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        _send_message(org_id, workspace_id, kb_id, assistant_id, conversation_id, headers)
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(Message).where(
                    Message.conversation_id == conversation_id, Message.role == "user"
                )
            )
            user_message_id = result.scalar_one().id

        response = client.post(
            _follow_up_url(
                org_id, workspace_id, kb_id, assistant_id, conversation_id, user_message_id
            ),
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_follow_up_questions_on_a_nonexistent_message_404s() -> None:
    email = "endpoint-test-followup-owner-3@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        response = client.post(
            _follow_up_url(
                org_id, workspace_id, kb_id, assistant_id, conversation_id, uuid.uuid4()
            ),
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


def test_follow_up_questions_requires_auth() -> None:
    response = client.post(
        _follow_up_url(
            uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        )
    )
    assert response.status_code == 401
