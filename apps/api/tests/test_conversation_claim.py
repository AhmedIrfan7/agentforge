"""Integration tests against the real FastAPI app for
routers/conversation.py:claim_conversation (roadmap step 193). Mirrors
test_public_conversation.py's own org/workspace/kb/public-assistant
setup (the anonymous side of the flow this step reconnects) plus
test_conversation_endpoints.py's own authenticated-request shape (the
identified side) -- a real anonymous conversation, created through the
real public router, then claimed through this router by a real,
separately-authenticated member of the same org.
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
from models.memory import Memory
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
        for model in (Memory, Conversation, Assistant, KnowledgeBase, Workspace, Membership):
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


def _new_org_workspace_kb_assistant(
    email: str, *, is_public: bool = True
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Claim Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Claim Test Org", "slug": f"endpoint-test-claim-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Claim Test Workspace", "slug": "endpoint-test-claim-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Claim Test KB", "slug": "endpoint-test-claim-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Claim Bot", "slug": "endpoint-test-claim-bot", "is_public": is_public},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    return org_id, workspace_id, kb_id, assistant_id, headers


def _conv_url(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    suffix: str = "",
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}/conversations{suffix}"
    )


def _create_anonymous_conversation(assistant_id: uuid.UUID) -> tuple[str, str]:
    response = client.post(f"/public/assistants/{assistant_id}/conversations")
    assert response.status_code == 201
    body = response.json()
    return body["conversation_id"], body["access_token"]


@pytest.mark.anyio
async def test_claim_an_anonymous_conversation_and_reconnect_memory() -> None:
    email = "endpoint-test-claim-owner-1@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        conversation_id, anonymous_token = _create_anonymous_conversation(assistant_id)

        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.email == email))
            owner_user = user_result.scalar_one()
            await set_tenant_context(session, org_id)
            session.add(
                Memory(
                    tenant_id=org_id,
                    scope="user",
                    user_id=owner_user.id,
                    content="Prefers concise answers.",
                    importance_score=0.9,
                )
            )
            await session.commit()

        claim_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, "/claim"),
            json={"anonymous_token": anonymous_token},
            headers=headers,
        )
        assert claim_response.status_code == 200
        body = claim_response.json()
        assert body["conversation"]["id"] == conversation_id
        assert body["conversation"]["user_id"] is not None
        assert len(body["memories"]) == 1
        assert body["memories"][0]["content"] == "Prefers concise answers."

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            conv_result = await session.execute(
                select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
            )
            conversation = conv_result.scalar_one()
            assert conversation.user_id is not None

        # Now claimed -- reachable through the normal authenticated list.
        list_response = client.get(
            _conv_url(org_id, workspace_id, kb_id, assistant_id), headers=headers
        )
        assert conversation_id in {item["id"] for item in list_response.json()["items"]}
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_claiming_with_an_invalid_token_401s() -> None:
    email = "endpoint-test-claim-owner-2@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, "/claim"),
            json={"anonymous_token": "not-a-real-token"},
            headers=headers,
        )
        assert response.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_claiming_with_a_real_access_token_as_the_anonymous_token_401s() -> None:
    """decode_anonymous_session_token's own type check -- a real user's
    access token (type "access") must never work as a claim credential
    either, same rejection routers/public_conversation.py's own
    message-send endpoint already relies on."""
    email = "endpoint-test-claim-owner-3@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, "/claim"),
            json={"anonymous_token": headers["Authorization"].removeprefix("Bearer ")},
            headers=headers,
        )
        assert response.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_claiming_an_already_claimed_conversation_404s() -> None:
    email = "endpoint-test-claim-owner-4@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        conversation_id, anonymous_token = _create_anonymous_conversation(assistant_id)

        first_claim = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, "/claim"),
            json={"anonymous_token": anonymous_token},
            headers=headers,
        )
        assert first_claim.status_code == 200

        second_claim = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, "/claim"),
            json={"anonymous_token": anonymous_token},
            headers=headers,
        )
        assert second_claim.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_claiming_a_conversation_under_the_wrong_assistant_404s() -> None:
    email = "endpoint-test-claim-owner-5@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        other_asst_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
            json={
                "name": "Other Public Bot",
                "slug": "endpoint-test-claim-other-bot",
                "is_public": True,
            },
            headers=headers,
        )
        other_assistant_id = uuid.UUID(other_asst_response.json()["id"])
        _conversation_id, anonymous_token = _create_anonymous_conversation(other_assistant_id)

        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, "/claim"),
            json={"anonymous_token": anonymous_token},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_non_member_cannot_claim_a_conversation() -> None:
    owner_email = "endpoint-test-claim-owner-6@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    outsider_email = "endpoint-test-claim-outsider@example.com"
    try:
        conversation_id, anonymous_token = _create_anonymous_conversation(assistant_id)
        outsider_token = signup_and_login(
            client,
            email=outsider_email,
            password="correct horse battery staple",
            full_name="Outsider",
        )

        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, "/claim"),
            json={"anonymous_token": anonymous_token},
            headers=auth_headers(outsider_token),
        )
        assert response.status_code == 403

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            conv_result = await session.execute(
                select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
            )
            conversation = conv_result.scalar_one()
            assert conversation.user_id is None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(outsider_email)


@pytest.mark.anyio
async def test_viewer_role_cannot_claim_a_conversation() -> None:
    """conversation:update excludes viewer, same reasoning
    test_conversation_endpoints.py's own update/delete viewer test
    already established -- claiming changes ownership, not a read."""
    owner_email = "endpoint-test-claim-owner-7@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    viewer_email = "endpoint-test-claim-viewer@example.com"
    try:
        conversation_id, anonymous_token = _create_anonymous_conversation(assistant_id)
        viewer_token = signup_and_login(
            client,
            email=viewer_email,
            password="correct horse battery staple",
            full_name="Viewer Member",
        )
        await _add_member(org_id, viewer_email, "viewer")

        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, "/claim"),
            json={"anonymous_token": anonymous_token},
            headers=auth_headers(viewer_token),
        )
        assert response.status_code == 403

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            conv_result = await session.execute(
                select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
            )
            conversation = conv_result.scalar_one()
            assert conversation.user_id is None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(viewer_email)
