"""Integration tests for the regenerate-response endpoint (roadmap
step 188). Reuses test_message_citations.py's own "seed a real Chunk
directly via the ORM" setup so a regenerated response has real,
checkable content (not just "No results found." every time), matching
that file's own precedent.
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
            Chunk,
            Document,
            Assistant,
            KnowledgeBase,
            Workspace,
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


async def _new_org_workspace_kb_assistant_conversation_with_chunk(
    email: str, *, chunk_text: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Regen Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Regen Test Org", "slug": f"endpoint-test-regen-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Regen Test WS", "slug": "endpoint-test-regen-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Regen Test KB", "slug": "endpoint-test-regen-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Regen Bot", "slug": "endpoint-test-regen-bot"},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    conv_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}/conversations",
        headers=headers,
    )
    conversation_id = uuid.UUID(conv_response.json()["id"])

    async with get_session() as session:
        await set_tenant_context(session, org_id)
        document = Document(
            tenant_id=org_id,
            knowledge_base_id=kb_id,
            title="Doc.txt",
            storage_key="regen-test/doc.txt",
            content_type="text/plain",
            size_bytes=len(chunk_text),
        )
        session.add(document)
        await session.flush()
        session.add(
            Chunk(
                tenant_id=org_id,
                document_id=document.id,
                text=chunk_text,
                start=0,
                end=len(chunk_text),
                index=0,
            )
        )
        await session.commit()

    return org_id, workspace_id, kb_id, assistant_id, conversation_id, headers


def _msg_url(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    suffix: str = "",
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
        f"/conversations/{conversation_id}/messages{suffix}"
    )


@pytest.mark.anyio
async def test_regenerate_produces_a_fresh_response_for_the_same_message_id() -> None:
    email = "endpoint-test-regen-owner-1@example.com"
    (
        org_id,
        workspace_id,
        kb_id,
        assistant_id,
        conversation_id,
        headers,
    ) = await _new_org_workspace_kb_assistant_conversation_with_chunk(
        email, chunk_text="Our refund policy allows returns within thirty days."
    )
    try:
        send_response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "refund policy"},
            headers=headers,
        )
        message_id = send_response.json()["id"]
        assert (
            send_response.json()["content"]
            == "Our refund policy allows returns within thirty days."
        )
        assert len(send_response.json()["citations"]) == 1

        regenerate_response = client.post(
            _msg_url(
                org_id,
                workspace_id,
                kb_id,
                assistant_id,
                conversation_id,
                f"/{message_id}/regenerate",
            ),
            headers=headers,
        )
        assert regenerate_response.status_code == 200
        body = regenerate_response.json()
        # Same message id -- updated in place, not a new row.
        assert body["id"] == message_id
        assert body["content"] == "Our refund policy allows returns within thirty days."
        assert len(body["citations"]) == 1

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(Message).where(Message.conversation_id == conversation_id)
            )
            messages = result.scalars().all()
            # Still exactly one user + one assistant message -- no new
            # row was created.
            assert len(messages) == 2
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_regenerate_requires_a_real_assistant_message() -> None:
    email = "endpoint-test-regen-owner-2@example.com"
    (
        org_id,
        workspace_id,
        kb_id,
        assistant_id,
        conversation_id,
        headers,
    ) = await _new_org_workspace_kb_assistant_conversation_with_chunk(
        email, chunk_text="irrelevant"
    )
    try:
        send_response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "hello"},
            headers=headers,
        )
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(Message).where(
                    Message.conversation_id == conversation_id, Message.role == "user"
                )
            )
            user_message_id = result.scalar_one().id

        # Trying to "regenerate" the USER's own turn must 404 -- same
        # not-found-not-forbidden precedent every other cross-resource
        # mismatch in this router already uses.
        response = client.post(
            _msg_url(
                org_id,
                workspace_id,
                kb_id,
                assistant_id,
                conversation_id,
                f"/{user_message_id}/regenerate",
            ),
            headers=headers,
        )
        assert response.status_code == 404
        assert send_response.status_code == 201
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_regenerate_a_nonexistent_message_404s() -> None:
    email = "endpoint-test-regen-owner-3@example.com"
    (
        org_id,
        workspace_id,
        kb_id,
        assistant_id,
        conversation_id,
        headers,
    ) = await _new_org_workspace_kb_assistant_conversation_with_chunk(
        email, chunk_text="irrelevant"
    )
    try:
        response = client.post(
            _msg_url(
                org_id,
                workspace_id,
                kb_id,
                assistant_id,
                conversation_id,
                f"/{uuid.uuid4()}/regenerate",
            ),
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_another_user_cannot_regenerate_someone_elses_message() -> None:
    owner_email = "endpoint-test-regen-owner-4@example.com"
    (
        org_id,
        workspace_id,
        kb_id,
        assistant_id,
        conversation_id,
        owner_headers,
    ) = await _new_org_workspace_kb_assistant_conversation_with_chunk(
        owner_email, chunk_text="Our refund policy allows returns within thirty days."
    )
    other_email = "endpoint-test-regen-other@example.com"
    try:
        send_response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "refund policy"},
            headers=owner_headers,
        )
        message_id = send_response.json()["id"]

        other_token = signup_and_login(
            client,
            email=other_email,
            password="correct horse battery staple",
            full_name="Other Owner",
        )
        await _add_member(org_id, other_email, "manager")

        response = client.post(
            _msg_url(
                org_id,
                workspace_id,
                kb_id,
                assistant_id,
                conversation_id,
                f"/{message_id}/regenerate",
            ),
            headers=auth_headers(other_token),
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(other_email)


def test_regenerate_requires_auth() -> None:
    response = client.post(
        _msg_url(
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            f"/{uuid.uuid4()}/regenerate",
        )
    )
    assert response.status_code == 401
