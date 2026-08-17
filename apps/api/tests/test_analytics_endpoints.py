"""Integration tests against the real FastAPI app for
routers/analytics.py (roadmap steps 243-245, each the first real
caller of its own analytics/agent.py:AnalyticsAgent method).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.agent_execution_log import AgentExecutionLog
from models.assistant import Assistant
from models.audit_log import AuditLog
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


async def _new_knowledge_base(org_id: uuid.UUID, headers: dict[str, str]) -> uuid.UUID:
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Analytics KB WS", "slug": "endpoint-test-analytics-kb-ws"},
        headers=headers,
    )
    workspace_id = ws_response.json()["id"]
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Analytics Standalone KB", "slug": "endpoint-test-analytics-standalone-kb"},
        headers=headers,
    )
    return uuid.UUID(kb_response.json()["id"])


async def _new_document(
    org_id: uuid.UUID, knowledge_base_id: uuid.UUID, *, slug: str, doc_metadata: dict[str, object]
) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        session.add(
            Document(
                tenant_id=org_id,
                knowledge_base_id=knowledge_base_id,
                title=f"Doc {slug}",
                status="embedded",
                storage_key=f"endpoint-test-analytics/{slug}",
                content_type="text/plain",
                size_bytes=10,
                doc_metadata=doc_metadata,
            )
        )
        await session.commit()


async def _new_execution_log(
    org_id: uuid.UUID, *, agent_name: str, status: str, latency_ms: float
) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        session.add(
            AgentExecutionLog(
                tenant_id=org_id, agent_name=agent_name, status=status, latency_ms=latency_ms
            )
        )
        await session.commit()


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (
            Message,
            Conversation,
            Document,
            AgentExecutionLog,
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


def _new_org(email: str) -> tuple[uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Analytics Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Analytics Test Org", "slug": f"endpoint-test-analytics-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


async def _new_assistant(org_id: uuid.UUID, headers: dict[str, str]) -> uuid.UUID:
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Analytics WS", "slug": "endpoint-test-analytics-ws"},
        headers=headers,
    )
    workspace_id = ws_response.json()["id"]
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Analytics KB", "slug": "endpoint-test-analytics-kb"},
        headers=headers,
    )
    kb_id = kb_response.json()["id"]
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Analytics Bot", "slug": "endpoint-test-analytics-bot"},
        headers=headers,
    )
    return uuid.UUID(asst_response.json()["id"])


async def _new_conversation_with_messages(
    org_id: uuid.UUID, assistant_id: uuid.UUID, *, message_count: int
) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        conversation = Conversation(tenant_id=org_id, assistant_id=assistant_id)
        session.add(conversation)
        await session.flush()
        for i in range(message_count):
            session.add(
                Message(
                    tenant_id=org_id,
                    conversation_id=conversation.id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"message {i}",
                )
            )
        await session.commit()


async def _add_member_with_role(org_id: uuid.UUID, email: str, role_name: str) -> dict[str, str]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name=role_name
    )
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        role_result = await session.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one()
        await set_tenant_context(session, org_id)
        session.add(
            Membership(tenant_id=org_id, user_id=user.id, workspace_id=None, role_id=role.id)
        )
        await session.commit()
    return auth_headers(token)


@pytest.mark.anyio
async def test_owner_can_read_real_conversation_metrics() -> None:
    email = "endpoint-test-analytics-owner-1@example.com"
    org_id, headers = _new_org(email)
    try:
        assistant_id = await _new_assistant(org_id, headers)
        await _new_conversation_with_messages(org_id, assistant_id, message_count=4)
        await _new_conversation_with_messages(org_id, assistant_id, message_count=2)

        response = client.get(f"/organizations/{org_id}/analytics/conversations", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total_conversations"] == 2
        assert body["total_messages"] == 6
        assert body["average_messages_per_conversation"] == 3.0
        assert body["conversations_last_7_days"] == 2
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_analyst_role_can_read_conversation_metrics() -> None:
    owner_email = "endpoint-test-analytics-owner-2@example.com"
    org_id, owner_headers = _new_org(owner_email)
    analyst_email = "endpoint-test-analytics-analyst@example.com"
    try:
        analyst_headers = await _add_member_with_role(org_id, analyst_email, "analyst")

        response = client.get(
            f"/organizations/{org_id}/analytics/conversations", headers=analyst_headers
        )
        assert response.status_code == 200
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(analyst_email)


@pytest.mark.anyio
async def test_owner_can_read_real_knowledge_metrics() -> None:
    email = "endpoint-test-analytics-owner-4@example.com"
    org_id, headers = _new_org(email)
    try:
        kb_id = await _new_knowledge_base(org_id, headers)
        await _new_document(
            org_id, kb_id, slug="dup", doc_metadata={"duplicate_document_ids": ["x"]}
        )
        await _new_document(org_id, kb_id, slug="clean", doc_metadata={})

        response = client.get(f"/organizations/{org_id}/analytics/knowledge", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total_documents"] == 2
        assert body["duplicate_document_count"] == 1
        # Neither document has a chunking_strategy set, and neither is
        # ever cited -- both count as unused, matching the same "no
        # signal yet" honesty knowledge_metrics() itself documents.
        assert body["low_confidence_document_count"] == 0
        assert body["unused_document_count"] == 2
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_read_knowledge_metrics() -> None:
    owner_email = "endpoint-test-analytics-owner-5@example.com"
    org_id, _owner_headers = _new_org(owner_email)
    end_user_email = "endpoint-test-analytics-enduser-kb@example.com"
    try:
        end_user_headers = await _add_member_with_role(org_id, end_user_email, "end_user")

        response = client.get(
            f"/organizations/{org_id}/analytics/knowledge", headers=end_user_headers
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(end_user_email)


@pytest.mark.anyio
async def test_owner_can_read_real_agent_performance_metrics() -> None:
    email = "endpoint-test-analytics-owner-6@example.com"
    org_id, headers = _new_org(email)
    try:
        await _new_execution_log(org_id, agent_name="retriever", status="success", latency_ms=100)
        await _new_execution_log(org_id, agent_name="retriever", status="failure", latency_ms=50)

        response = client.get(
            f"/organizations/{org_id}/analytics/agent-performance", headers=headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["per_agent"] == [
            {
                "agent_name": "retriever",
                "execution_count": 2,
                "success_rate": 0.5,
                "average_latency_ms": 75.0,
            }
        ]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_read_agent_performance_metrics() -> None:
    owner_email = "endpoint-test-analytics-owner-7@example.com"
    org_id, _owner_headers = _new_org(owner_email)
    end_user_email = "endpoint-test-analytics-enduser-perf@example.com"
    try:
        end_user_headers = await _add_member_with_role(org_id, end_user_email, "end_user")

        response = client.get(
            f"/organizations/{org_id}/analytics/agent-performance", headers=end_user_headers
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(end_user_email)
        await _cleanup_user(owner_email)
        await _cleanup_user(end_user_email)


@pytest.mark.anyio
async def test_end_user_role_cannot_read_conversation_metrics() -> None:
    owner_email = "endpoint-test-analytics-owner-3@example.com"
    org_id, _owner_headers = _new_org(owner_email)
    end_user_email = "endpoint-test-analytics-enduser@example.com"
    try:
        end_user_headers = await _add_member_with_role(org_id, end_user_email, "end_user")

        response = client.get(
            f"/organizations/{org_id}/analytics/conversations", headers=end_user_headers
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(end_user_email)


@pytest.mark.anyio
async def test_metrics_route_requires_auth() -> None:
    response = client.get(f"/organizations/{uuid.uuid4()}/analytics/conversations")
    assert response.status_code == 401
