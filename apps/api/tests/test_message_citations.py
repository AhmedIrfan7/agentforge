"""Integration tests for citation display in chat responses (roadmap
step 187). Seeds a real Chunk directly via the ORM (same "real chunk
rows added directly via the ORM" precedent test_retrieval_endpoints.py
already established at steps 120-122) so a real keyword-search hit in
orchestrator.py:_execute_node has something real to cite, then sends a
real message through the real HTTP endpoint and checks the persisted
citation.
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


async def _new_org_workspace_kb_assistant_conversation_with_chunk(
    email: str, *, chunk_text: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Citation Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Citation Test Org", "slug": f"endpoint-test-citation-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Citation Test WS", "slug": "endpoint-test-citation-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Citation Test KB", "slug": "endpoint-test-citation-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Citation Bot", "slug": "endpoint-test-citation-bot"},
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
            title="Refund Policy.txt",
            storage_key="citation-test/doc.txt",
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
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}"
        f"/conversations/{conversation_id}/messages"
    )


@pytest.mark.anyio
async def test_a_real_retrieval_hit_produces_a_real_citation() -> None:
    email = "endpoint-test-citation-owner-1@example.com"
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
        response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "refund policy"},
            headers=headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["content"] == "Our refund policy allows returns within thirty days."
        assert len(body["citations"]) == 1
        citation = body["citations"][0]
        assert citation["document_title"] == "Refund Policy.txt"
        assert citation["knowledge_base_name"] == "Citation Test KB"
        assert citation["section"] is None

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(Message).where(
                    Message.conversation_id == conversation_id, Message.role == "assistant"
                )
            )
            message = result.scalar_one()
            assert len(message.citations) == 1
            assert message.citations[0]["document_title"] == "Refund Policy.txt"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_no_retrieval_hit_means_no_citations() -> None:
    email = "endpoint-test-citation-owner-2@example.com"
    (
        org_id,
        workspace_id,
        kb_id,
        assistant_id,
        conversation_id,
        headers,
    ) = await _new_org_workspace_kb_assistant_conversation_with_chunk(
        email, chunk_text="Completely unrelated content about shipping times."
    )
    try:
        response = client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "something nothing matches xyzzyzzy"},
            headers=headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["content"] == "No results found."
        assert body["citations"] == []
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_user_messages_never_have_citations() -> None:
    email = "endpoint-test-citation-owner-3@example.com"
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
        client.post(
            _msg_url(org_id, workspace_id, kb_id, assistant_id, conversation_id),
            json={"content": "refund policy"},
            headers=headers,
        )

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(Message).where(
                    Message.conversation_id == conversation_id, Message.role == "user"
                )
            )
            user_message = result.scalar_one()
            assert user_message.citations == []
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
