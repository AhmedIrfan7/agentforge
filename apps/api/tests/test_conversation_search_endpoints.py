"""Integration tests against the real FastAPI app for
routers/conversation.py's search endpoints (roadmap step 183).
Mirrors test_retrieval_endpoints.py's own "real chunk rows with real
embeddings added directly via the ORM, fake embedding provider swapped
in for query-time embedding" approach (120-122) -- proves real
end-to-end ranking through the real endpoint without a real
OPENAI_API_KEY.
"""

import uuid
from dataclasses import dataclass

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


@dataclass
class _FakeEmbeddingProvider:
    name: str = "fake"
    dimensions: int = 1536
    vectors_by_text: dict[str, list[float]] | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        table = self.vectors_by_text or {}
        return [table.get(text, [0.0] * self.dimensions) for text in texts]


def _vector(*, lead: float) -> list[float]:
    return [lead] + [0.01] * 1535


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


def _new_org_workspace_kb_assistant(
    email: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Search Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Conv Search Test Org", "slug": f"endpoint-test-convsearch-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Conv Search WS", "slug": "endpoint-test-convsearch-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Conv Search KB", "slug": "endpoint-test-convsearch-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Search Bot", "slug": "endpoint-test-convsearch-bot"},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    return org_id, workspace_id, kb_id, assistant_id, headers


def _search_url(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    mechanism: str,
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}/conversations/search/{mechanism}"
    )


async def _seed_message(
    org_id: uuid.UUID,
    assistant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    content: str,
    embedding: list[float] | None = None,
) -> uuid.UUID:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        conversation = Conversation(tenant_id=org_id, assistant_id=assistant_id, user_id=user_id)
        session.add(conversation)
        await session.flush()
        message = Message(
            tenant_id=org_id,
            conversation_id=conversation.id,
            role="user",
            content=content,
            embedding=embedding,
        )
        session.add(message)
        await session.commit()
        return conversation.id


async def _real_user_id(email: str) -> uuid.UUID:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one().id


def test_search_routes_require_auth() -> None:
    for mechanism in ("keyword", "semantic"):
        response = client.post(
            _search_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), mechanism),
            json={"query": "refund"},
        )
        assert response.status_code == 401


@pytest.mark.anyio
async def test_keyword_search_finds_a_real_message_by_content() -> None:
    email = "endpoint-test-convsearch-owner-1@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        user_id = await _real_user_id(email)
        await _seed_message(
            org_id, assistant_id, user_id, content="Our refund policy allows 30 days."
        )
        await _seed_message(org_id, assistant_id, user_id, content="Business hours are 9 to 5.")

        response = client.post(
            _search_url(org_id, workspace_id, kb_id, assistant_id, "keyword"),
            json={"query": "refund policy"},
            headers=headers,
        )
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["content"] == "Our refund policy allows 30 days."
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_semantic_search_ranks_the_closest_message_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeEmbeddingProvider(vectors_by_text={"find the refund answer": _vector(lead=1.0)})
    monkeypatch.setattr("routers.conversation._embedding_provider", fake)

    email = "endpoint-test-convsearch-owner-2@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        user_id = await _real_user_id(email)
        await _seed_message(
            org_id,
            assistant_id,
            user_id,
            content="Close match about refunds.",
            embedding=_vector(lead=0.99),
        )
        await _seed_message(
            org_id,
            assistant_id,
            user_id,
            content="Unrelated business hours info.",
            embedding=_vector(lead=-1.0),
        )
        # No embedding yet -- must be excluded, same real gap Chunk's
        # own dense search already documents for a just-created row.
        await _seed_message(org_id, assistant_id, user_id, content="Never embedded.")

        response = client.post(
            _search_url(org_id, workspace_id, kb_id, assistant_id, "semantic"),
            json={"query": "find the refund answer"},
            headers=headers,
        )
        assert response.status_code == 200
        results = response.json()
        # Both embedded messages come back (top_k defaults to 10) --
        # the real behavior under test is ranking (closest first) and
        # excluding the not-yet-embedded row entirely, not a result
        # count.
        contents = [r["content"] for r in results]
        assert contents == ["Close match about refunds.", "Unrelated business hours info."]
        assert "Never embedded." not in contents
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_search_only_returns_the_callers_own_messages() -> None:
    email = "endpoint-test-convsearch-owner-3@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    other_email = "endpoint-test-convsearch-other@example.com"
    try:
        user_id = await _real_user_id(email)
        await _seed_message(org_id, assistant_id, user_id, content="My own refund question.")

        signup_and_login(
            client,
            email=other_email,
            password="correct horse battery staple",
            full_name="Other User",
        )
        other_user_id = await _real_user_id(other_email)
        await _seed_message(
            org_id, assistant_id, other_user_id, content="Someone else's refund question."
        )

        response = client.post(
            _search_url(org_id, workspace_id, kb_id, assistant_id, "keyword"),
            json={"query": "refund"},
            headers=headers,
        )
        assert response.status_code == 200
        results = response.json()
        assert [r["content"] for r in results] == ["My own refund question."]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
        await _cleanup_user(other_email)


@pytest.mark.anyio
async def test_viewer_role_can_search_conversations() -> None:
    """conversation:read (reused by search) includes viewer, unlike
    conversation:create/message:create."""
    owner_email = "endpoint-test-convsearch-owner-4@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    viewer_email = "endpoint-test-convsearch-viewer@example.com"
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
            session.add(
                Membership(
                    tenant_id=org_id,
                    user_id=viewer_user.id,
                    workspace_id=None,
                    role_id=viewer_role.id,
                )
            )
            await session.commit()

        response = client.post(
            _search_url(org_id, workspace_id, kb_id, assistant_id, "keyword"),
            json={"query": "anything"},
            headers=auth_headers(viewer_token),
        )
        assert response.status_code == 200
        assert response.json() == []
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(viewer_email)
