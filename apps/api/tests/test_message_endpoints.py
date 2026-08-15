"""Integration tests against the real FastAPI app for
routers/conversation.py's message-send endpoint (roadmap step 179).
Mirrors test_conversation_endpoints.py's own shape (178), one nesting
level deeper -- .../conversations/{conversation_id}/messages.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.assistant import Assistant
from models.audit_log import AuditLog
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.membership import Membership
from models.message import Message
from models.organization import Organization
from models.role import Role
from models.session import Session
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (
            Message,
            Conversation,
            Assistant,
            KnowledgeBase,
            Workspace,
            AuditLog,
            Membership,
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


async def _add_member(org_id: uuid.UUID, email: str, role_name: str) -> None:
    async with get_session() as session:
        user_result = await session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one()
        role_result = await session.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one()
        await set_tenant_context(session, org_id)
        session.add(
            Membership(tenant_id=org_id, user_id=user.id, workspace_id=None, role_id=role.id)
        )
        await session.commit()


def _new_org_workspace_kb_assistant_conversation(
    email: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Msg Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Message Test Org", "slug": f"endpoint-test-msg-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Msg Test Workspace", "slug": "endpoint-test-msg-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Msg Test KB", "slug": "endpoint-test-msg-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Msg Bot", "slug": "endpoint-test-msg-bot"},
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


def _msg_url(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
        f"/conversations/{conversation_id}/messages"
    )


def test_message_routes_require_auth() -> None:
    response = client.post(
        _msg_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()),
        json={"content": "hello"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_send_message_persists_both_turns_and_returns_the_assistant_reply() -> None:
    email = "endpoint-test-msg-owner-1@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "What is your refund policy?"},
            headers=headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["conversation_id"] == str(conversation_id)
        assert body["role"] == "assistant"
        assert body["content"]
        # Real markdown->HTML rendering (step 185), not just a copy of
        # the raw content.
        assert body["content_html"] == f"<p>{body['content']}</p>"
        # No documents in this KB -- no real retrieval hit, so no
        # citations (step 187's own real test coverage for the hit
        # case lives in test_message_citations.py).
        assert body["citations"] == []

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
            assert messages[0].content == "What is your refund policy?"
            assert messages[1].role == "assistant"

            audit_result = await session.execute(
                select(AuditLog).where(AuditLog.action == "message.create")
            )
            assert audit_result.scalar_one_or_none() is not None

            # The conversation started "new" (178) -- the first message
            # sent into it is the one real, automatic status transition
            # this codebase triggers today (181).
            conversation = await session.get(Conversation, conversation_id)
            assert conversation is not None
            assert conversation.status == "active"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_send_message_rejects_empty_content() -> None:
    email = "endpoint-test-msg-owner-2@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": ""},
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_another_users_conversation_is_not_reachable() -> None:
    """Conversation is user-owned, not just tenant-owned -- another
    member of the SAME org (with real conversation:create/message:create
    permission) still can't send into a conversation they don't own."""
    owner_email = "endpoint-test-msg-owner-3@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, _owner_headers = (
        _new_org_workspace_kb_assistant_conversation(owner_email)
    )
    other_email = "endpoint-test-msg-other-owner@example.com"
    try:
        other_token = signup_and_login(
            client,
            email=other_email,
            password="correct horse battery staple",
            full_name="Other Owner",
        )
        await _add_member(org_id, other_email, "manager")

        response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "Trying to butt in."},
            headers=auth_headers(other_token),
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(other_email)


@pytest.mark.anyio
async def test_viewer_role_cannot_send_message() -> None:
    """viewer lacks message:create -- deliberately made the REAL owner
    of the conversation (via direct ORM creation, since viewer also
    lacks conversation:create and can't make one through the real
    endpoint) so this test isolates the permission check alone, rather
    than being ambiguous between a 403 (permission) and a 404
    (ownership mismatch)."""
    owner_email = "endpoint-test-msg-owner-4@example.com"
    org_id, workspace_id, kb_id, assistant_id, _conversation_id, _owner_headers = (
        _new_org_workspace_kb_assistant_conversation(owner_email)
    )
    member_email = "endpoint-test-msg-viewer@example.com"
    try:
        member_token = signup_and_login(
            client,
            email=member_email,
            password="correct horse battery staple",
            full_name="Viewer Member",
        )
        await _add_member(org_id, member_email, "viewer")

        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.email == member_email))
            viewer_user = user_result.scalar_one()
            await set_tenant_context(session, org_id)
            conversation = Conversation(
                tenant_id=org_id, assistant_id=assistant_id, user_id=viewer_user.id
            )
            session.add(conversation)
            await session.commit()
            own_conversation_id = conversation.id

        response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, own_conversation_id),
            json={"content": "Should fail."},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(member_email)
