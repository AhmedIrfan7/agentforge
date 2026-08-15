"""Integration tests for the feedback endpoint (roadmap step 189).
Mirrors test_message_endpoints.py's own setup shape (no chunk seeding
needed -- feedback rates a reply's usefulness, not its retrieval
content, so "No results found." is a fine thing to rate).
"""

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
from models.role import Role
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
        client, email=email, password="correct horse battery staple", full_name="Feedback Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Feedback Test Org", "slug": f"endpoint-test-feedback-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Feedback Test WS", "slug": "endpoint-test-feedback-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Feedback Test KB", "slug": "endpoint-test-feedback-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Feedback Bot", "slug": "endpoint-test-feedback-bot"},
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


def _feedback_url(
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
        f"/conversations/{conversation_id}/messages/{message_id}/feedback"
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
        json={"content": "hello"},
        headers=headers,
    )
    message_id: str = response.json()["id"]
    return message_id


@pytest.mark.anyio
async def test_set_and_read_back_feedback() -> None:
    email = "endpoint-test-feedback-owner-1@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        message_id = _send_message(
            org_id, workspace_id, kb_id, assistant_id, conversation_id, headers
        )

        response = client.put(
            _feedback_url(org_id, workspace_id, kb_id, assistant_id, conversation_id, message_id),
            json={"feedback_type": "not_helpful"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["feedback_type"] == "not_helpful"

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            message = await session.get(Message, uuid.UUID(message_id))
            assert message is not None
            assert message.feedback_type == "not_helpful"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_every_real_feedback_type_is_accepted() -> None:
    email = "endpoint-test-feedback-owner-2@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        message_id = _send_message(
            org_id, workspace_id, kb_id, assistant_id, conversation_id, headers
        )
        for feedback_type in (
            "helpful",
            "not_helpful",
            "incorrect",
            "incomplete",
            "outdated",
            "missing_citation",
            "poor_retrieval",
            "hallucination",
        ):
            response = client.put(
                _feedback_url(
                    org_id, workspace_id, kb_id, assistant_id, conversation_id, message_id
                ),
                json={"feedback_type": feedback_type},
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json()["feedback_type"] == feedback_type
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_an_invalid_feedback_type_is_rejected() -> None:
    email = "endpoint-test-feedback-owner-3@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        message_id = _send_message(
            org_id, workspace_id, kb_id, assistant_id, conversation_id, headers
        )
        response = client.put(
            _feedback_url(org_id, workspace_id, kb_id, assistant_id, conversation_id, message_id),
            json={"feedback_type": "not_a_real_type"},
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_clear_feedback() -> None:
    email = "endpoint-test-feedback-owner-4@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        message_id = _send_message(
            org_id, workspace_id, kb_id, assistant_id, conversation_id, headers
        )
        client.put(
            _feedback_url(org_id, workspace_id, kb_id, assistant_id, conversation_id, message_id),
            json={"feedback_type": "helpful"},
            headers=headers,
        )

        delete_response = client.delete(
            _feedback_url(org_id, workspace_id, kb_id, assistant_id, conversation_id, message_id),
            headers=headers,
        )
        assert delete_response.status_code == 204

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            message = await session.get(Message, uuid.UUID(message_id))
            assert message is not None
            assert message.feedback_type is None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_feedback_on_a_user_message_404s() -> None:
    email = "endpoint-test-feedback-owner-5@example.com"
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

        response = client.put(
            _feedback_url(
                org_id, workspace_id, kb_id, assistant_id, conversation_id, user_message_id
            ),
            json={"feedback_type": "helpful"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_feedback_on_a_nonexistent_message_404s() -> None:
    email = "endpoint-test-feedback-owner-6@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        response = client.put(
            _feedback_url(org_id, workspace_id, kb_id, assistant_id, conversation_id, uuid.uuid4()),
            json={"feedback_type": "helpful"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_another_user_cannot_give_feedback_on_someone_elses_message() -> None:
    owner_email = "endpoint-test-feedback-owner-7@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, owner_headers = (
        _new_org_workspace_kb_assistant_conversation(owner_email)
    )
    other_email = "endpoint-test-feedback-other@example.com"
    try:
        message_id = _send_message(
            org_id, workspace_id, kb_id, assistant_id, conversation_id, owner_headers
        )

        other_token = signup_and_login(
            client,
            email=other_email,
            password="correct horse battery staple",
            full_name="Other Owner",
        )
        await _add_member(org_id, other_email, "manager")

        response = client.put(
            _feedback_url(org_id, workspace_id, kb_id, assistant_id, conversation_id, message_id),
            json={"feedback_type": "helpful"},
            headers=auth_headers(other_token),
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(other_email)


def test_feedback_requires_auth() -> None:
    response = client.put(
        _feedback_url(
            uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        ),
        json={"feedback_type": "helpful"},
    )
    assert response.status_code == 401
