"""Integration tests for anonymous-session (pre-auth visitor)
conversation endpoints (roadmap step 192). Sets up a real org/
workspace/knowledge-base/assistant through the real authenticated
endpoints (an org owner has to actually create and mark an assistant
public first), then exercises the SEPARATE, unauthenticated
/public/... router the rest of this file is really about.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

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
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Message, Conversation, Chunk, Document, Assistant, KnowledgeBase, Workspace):
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


def _new_org_workspace_kb_assistant(email: str, *, is_public: bool) -> tuple[uuid.UUID, uuid.UUID]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Public Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Public Test Org", "slug": f"endpoint-test-public-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Public Test WS", "slug": "endpoint-test-public-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Public Test KB", "slug": "endpoint-test-public-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Public Bot", "slug": "endpoint-test-public-bot", "is_public": is_public},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    return org_id, assistant_id


def _public_url(assistant_id: uuid.UUID, suffix: str = "") -> str:
    return f"/public/assistants/{assistant_id}/conversations{suffix}"


def _new_org_workspace_kb_assistant_and_headers(
    email: str, *, is_public: bool
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """Same real org/workspace/kb/assistant chain as
    _new_org_workspace_kb_assistant, plus the owner's own auth headers
    -- needed only by the allowed_domains tests below, which have to
    PATCH the org's real security-settings as its real owner. Kept
    separate rather than changing the existing helper's return shape,
    which every other test in this file already unpacks as a 2-tuple.
    """
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Public Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Public Test Org", "slug": f"endpoint-test-public-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Public Test WS", "slug": "endpoint-test-public-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Public Test KB", "slug": "endpoint-test-public-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Public Bot", "slug": "endpoint-test-public-bot", "is_public": is_public},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    return org_id, assistant_id, headers


@pytest.mark.anyio
async def test_create_anonymous_conversation_for_a_public_assistant() -> None:
    email = "endpoint-test-public-owner-1@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email, is_public=True)
    try:
        response = client.post(_public_url(assistant_id))
        assert response.status_code == 201
        body = response.json()
        assert "conversation_id" in body
        assert isinstance(body["access_token"], str)
        assert body["access_token"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_creating_an_anonymous_conversation_is_rejected_for_a_non_public_assistant() -> None:
    email = "endpoint-test-public-owner-2@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email, is_public=False)
    try:
        response = client.post(_public_url(assistant_id))
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_creating_an_anonymous_conversation_for_a_nonexistent_assistant_404s() -> None:
    response = client.post(_public_url(uuid.uuid4()))
    assert response.status_code == 404


@pytest.mark.anyio
async def test_full_anonymous_chat_flow_with_a_real_citation() -> None:
    email = "endpoint-test-public-owner-3@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email, is_public=True)
    try:
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            asst_result = await session.execute(
                select(Assistant).where(Assistant.id == assistant_id)
            )
            assistant = asst_result.scalar_one()
            document = Document(
                tenant_id=org_id,
                knowledge_base_id=assistant.knowledge_base_id,
                title="Public Refund Policy.txt",
                storage_key="public-test/doc.txt",
                content_type="text/plain",
                size_bytes=50,
            )
            session.add(document)
            await session.flush()
            text = "Our refund policy allows returns within thirty days."
            session.add(
                Chunk(
                    tenant_id=org_id,
                    document_id=document.id,
                    text=text,
                    start=0,
                    end=len(text),
                    index=0,
                )
            )
            await session.commit()

        create_response = client.post(_public_url(assistant_id))
        assert create_response.status_code == 201
        conversation_id = create_response.json()["conversation_id"]
        access_token = create_response.json()["access_token"]

        message_response = client.post(
            _public_url(assistant_id, f"/{conversation_id}/messages"),
            json={"content": "refund policy"},
            headers=auth_headers(access_token),
        )
        assert message_response.status_code == 201
        body = message_response.json()
        assert body["content"] == "Our refund policy allows returns within thirty days."
        assert len(body["citations"]) == 1
        assert body["citations"][0]["document_title"] == "Public Refund Policy.txt"

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            conv_result = await session.execute(
                select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
            )
            conversation = conv_result.scalar_one()
            assert conversation.user_id is None
            assert conversation.status == "active"

            msg_result = await session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
            messages = msg_result.scalars().all()
            assert len(messages) == 2
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_sending_a_message_with_no_token_401s() -> None:
    email = "endpoint-test-public-owner-4@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email, is_public=True)
    try:
        create_response = client.post(_public_url(assistant_id))
        conversation_id = create_response.json()["conversation_id"]

        response = client.post(
            _public_url(assistant_id, f"/{conversation_id}/messages"),
            json={"content": "hello"},
        )
        assert response.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_a_token_for_a_different_conversation_401s() -> None:
    email = "endpoint-test-public-owner-5@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email, is_public=True)
    try:
        first = client.post(_public_url(assistant_id))
        second = client.post(_public_url(assistant_id))
        second_conversation_id = second.json()["conversation_id"]
        first_token = first.json()["access_token"]

        response = client.post(
            _public_url(assistant_id, f"/{second_conversation_id}/messages"),
            json={"content": "hello"},
            headers=auth_headers(first_token),
        )
        assert response.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_a_real_authenticated_access_token_is_rejected_here() -> None:
    """decode_anonymous_session_token's own type check -- a real user's
    access token (type "access") must never work as an anonymous
    session credential."""
    email = "endpoint-test-public-owner-6@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email, is_public=True)
    try:
        real_user_token = signup_and_login(
            client,
            email="endpoint-test-public-realuser@example.com",
            password="correct horse battery staple",
            full_name="Real User",
        )
        create_response = client.post(_public_url(assistant_id))
        conversation_id = create_response.json()["conversation_id"]

        response = client.post(
            _public_url(assistant_id, f"/{conversation_id}/messages"),
            json={"content": "hello"},
            headers=auth_headers(real_user_token),
        )
        assert response.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
        await _cleanup_user("endpoint-test-public-realuser@example.com")


@pytest.mark.anyio
async def test_a_conversation_that_somehow_has_a_real_user_id_404s() -> None:
    """Defense in depth for get_anonymous_conversation's own
    `conversation.user_id is not None` check -- a real, valid,
    correctly-scoped anonymous token must still be rejected if the
    conversation it names isn't genuinely anonymous."""
    email = "endpoint-test-public-owner-7@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email, is_public=True)
    try:
        create_response = client.post(_public_url(assistant_id))
        conversation_id = create_response.json()["conversation_id"]
        access_token = create_response.json()["access_token"]

        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.email == email))
            owner_user = user_result.scalar_one()
            await set_tenant_context(session, org_id)
            conv_result = await session.execute(
                select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
            )
            conversation = conv_result.scalar_one()
            conversation.user_id = owner_user.id
            await session.commit()

        response = client.post(
            _public_url(assistant_id, f"/{conversation_id}/messages"),
            json={"content": "hello"},
            headers=auth_headers(access_token),
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_allowed_domains_blocks_a_disallowed_origin() -> None:
    email = "endpoint-test-public-owner-8@example.com"
    org_id, assistant_id, headers = _new_org_workspace_kb_assistant_and_headers(
        email, is_public=True
    )
    try:
        patch_response = client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"allowed_domains": ["example.com"]},
            headers=headers,
        )
        assert patch_response.status_code == 200

        response = client.post(_public_url(assistant_id), headers={"Origin": "https://evil.com"})
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_allowed_domains_allows_a_matching_origin_and_its_subdomains() -> None:
    email = "endpoint-test-public-owner-9@example.com"
    org_id, assistant_id, headers = _new_org_workspace_kb_assistant_and_headers(
        email, is_public=True
    )
    try:
        client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"allowed_domains": ["example.com"]},
            headers=headers,
        )

        exact = client.post(_public_url(assistant_id), headers={"Origin": "https://example.com"})
        assert exact.status_code == 201

        subdomain = client.post(
            _public_url(assistant_id), headers={"Origin": "https://widget.example.com"}
        )
        assert subdomain.status_code == 201
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_allowed_domains_allows_requests_with_no_origin_header() -> None:
    """Honest, documented limitation (routers/public_conversation.py's
    own docstring): a request with no Origin header at all (any non-
    browser HTTP client) is allowed through regardless of
    allowed_domains -- this feature constrains BROWSER-based embedding
    on an unauthorized site, not a general API firewall."""
    email = "endpoint-test-public-owner-10@example.com"
    org_id, assistant_id, headers = _new_org_workspace_kb_assistant_and_headers(
        email, is_public=True
    )
    try:
        client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"allowed_domains": ["example.com"]},
            headers=headers,
        )

        response = client.post(_public_url(assistant_id))
        assert response.status_code == 201
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_empty_allowed_domains_permits_any_origin() -> None:
    email = "endpoint-test-public-owner-11@example.com"
    org_id, assistant_id = _new_org_workspace_kb_assistant(email, is_public=True)
    try:
        response = client.post(
            _public_url(assistant_id), headers={"Origin": "https://anything-at-all.com"}
        )
        assert response.status_code == 201
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
