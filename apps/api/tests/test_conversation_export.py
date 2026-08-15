"""Integration tests for the conversation-export endpoint (roadmap
step 191). Mirrors test_message_endpoints.py's own setup shape.
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
        client, email=email, password="correct horse battery staple", full_name="Export Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Export Test Org", "slug": f"endpoint-test-export-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Export Test WS", "slug": "endpoint-test-export-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Export Test KB", "slug": "endpoint-test-export-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Export Bot", "slug": "endpoint-test-export-bot"},
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


def _export_url(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
        f"/conversations/{conversation_id}/export"
    )


@pytest.mark.anyio
async def test_export_as_json_includes_the_full_transcript() -> None:
    email = "endpoint-test-export-owner-1@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}"
            f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
            f"/conversations/{conversation_id}/messages",
            json={"content": "What is your refund policy?"},
            headers=headers,
        )

        response = client.get(
            _export_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            headers=headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert "attachment" in response.headers["content-disposition"]
        assert "conversation.json" in response.headers["content-disposition"]

        body = response.json()
        assert body["conversation"]["id"] == str(conversation_id)
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][0]["content"] == "What is your refund policy?"
        assert body["messages"][1]["role"] == "assistant"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_export_as_markdown_renders_a_real_document() -> None:
    email = "endpoint-test-export-owner-2@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}"
            f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
            f"/conversations/{conversation_id}/messages",
            json={"content": "What is your refund policy?"},
            headers=headers,
        )

        response = client.get(
            f"{_export_url(org_id, workspace_id, kb_id, assistant_id, conversation_id)}"
            "?format=markdown",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert "attachment" in response.headers["content-disposition"]
        assert "conversation.md" in response.headers["content-disposition"]

        text = response.text
        assert text.startswith("# Conversation with Export Bot")
        assert "## User" in text
        assert "What is your refund policy?" in text
        assert "## Assistant" in text
        assert "No results found." in text
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_export_uses_conversation_title_when_set() -> None:
    email = "endpoint-test-export-owner-3@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        client.patch(
            f"/organizations/{org_id}/workspaces/{workspace_id}"
            f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
            f"/conversations/{conversation_id}",
            json={"title": "Refund questions"},
            headers=headers,
        )

        response = client.get(
            f"{_export_url(org_id, workspace_id, kb_id, assistant_id, conversation_id)}"
            "?format=markdown",
            headers=headers,
        )
        assert response.text.startswith("# Refund questions")
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_export_an_empty_conversation() -> None:
    email = "endpoint-test-export-owner-4@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, headers = (
        _new_org_workspace_kb_assistant_conversation(email)
    )
    try:
        response = client.get(
            _export_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["messages"] == []
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_export_of_another_users_conversation_404s() -> None:
    owner_email = "endpoint-test-export-owner-5@example.com"
    org_id, workspace_id, kb_id, assistant_id, conversation_id, _owner_headers = (
        _new_org_workspace_kb_assistant_conversation(owner_email)
    )
    other_email = "endpoint-test-export-other@example.com"
    try:
        other_token = signup_and_login(
            client,
            email=other_email,
            password="correct horse battery staple",
            full_name="Other Owner",
        )
        await _add_member(org_id, other_email, "manager")

        response = client.get(
            _export_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            headers=auth_headers(other_token),
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(other_email)


@pytest.mark.anyio
async def test_viewer_role_can_export_a_conversation() -> None:
    """conversation:read (reused by export) includes viewer, same
    precedent list/search already established."""
    owner_email = "endpoint-test-export-owner-6@example.com"
    org_id, workspace_id, kb_id, assistant_id, _conversation_id, _owner_headers = (
        _new_org_workspace_kb_assistant_conversation(owner_email)
    )
    viewer_email = "endpoint-test-export-viewer@example.com"
    try:
        viewer_token = signup_and_login(
            client,
            email=viewer_email,
            password="correct horse battery staple",
            full_name="Viewer Member",
        )
        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.email == viewer_email))
            viewer_user = user_result.scalar_one()
            role_result = await session.execute(select(Role).where(Role.name == "viewer"))
            viewer_role = role_result.scalar_one()
            await set_tenant_context(session, org_id)
            conversation = Conversation(
                tenant_id=org_id, assistant_id=assistant_id, user_id=viewer_user.id
            )
            session.add(conversation)
            session.add(
                Membership(
                    tenant_id=org_id,
                    user_id=viewer_user.id,
                    workspace_id=None,
                    role_id=viewer_role.id,
                )
            )
            await session.commit()
            own_conversation_id = conversation.id

        response = client.get(
            _export_url(org_id, workspace_id, kb_id, assistant_id, own_conversation_id),
            headers=auth_headers(viewer_token),
        )
        assert response.status_code == 200
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(viewer_email)


def test_export_requires_auth() -> None:
    response = client.get(
        _export_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    )
    assert response.status_code == 401
