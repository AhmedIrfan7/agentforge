"""Integration tests against the real FastAPI app for
routers/retrieval.py (roadmap step 120).

Real org/workspace/knowledge-base/document setup through the real HTTP
endpoints, real Chunk rows with real embeddings added directly via the
ORM (no live worker needed -- matches the chunk-injection pattern
test_document_endpoints.py's own delete test already established), and
routers.retrieval._embedding_provider swapped for a fake so this can
prove real end-to-end ranking through the real endpoint without a real
OPENAI_API_KEY.
"""

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


@dataclass
class _FakeEmbeddingProvider:
    """Maps a query string to a hand-picked vector via a lookup table,
    so a test can control exactly which chunk should rank first --
    same "real class implementing the Protocol, not a mock" reasoning
    every other provider fake in this project already uses."""

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
        for model in (Chunk, Document, KnowledgeBase, Workspace, AuditLog, Membership):
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
        if user is not None:
            await session.delete(user)
            await session.commit()


def _new_org_with_kb(email: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Retrieval Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Retrieval Test Org", "slug": f"endpoint-test-retrieval-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Retrieval Test WS", "slug": "endpoint-test-retrieval-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Retrieval Test KB", "slug": "endpoint-test-retrieval-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    return org_id, workspace_id, kb_id, headers


def _search_url(org_id: uuid.UUID, workspace_id: uuid.UUID, kb_id: uuid.UUID) -> str:
    return f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/search"


@pytest.mark.anyio
async def test_dense_search_returns_the_closest_chunk_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "routers.retrieval._embedding_provider",
        _FakeEmbeddingProvider(vectors_by_text={"find the near chunk": _vector(lead=1.0)}),
    )

    email = "endpoint-test-retrieval-owner-1@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        document_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/documents",
            files={"file": ("doc.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = uuid.UUID(document_response.json()["id"])

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            session.add_all(
                [
                    Chunk(
                        tenant_id=org_id,
                        document_id=document_id,
                        text="far chunk",
                        start=0,
                        end=1,
                        index=0,
                        embedding=_vector(lead=-1.0),
                    ),
                    Chunk(
                        tenant_id=org_id,
                        document_id=document_id,
                        text="near chunk",
                        start=1,
                        end=2,
                        index=1,
                        embedding=_vector(lead=0.9),
                    ),
                ]
            )
            await session.commit()

        response = client.post(
            _search_url(org_id, workspace_id, kb_id),
            json={"query": "find the near chunk", "top_k": 5},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["text"] == "near chunk"
        assert body[0]["document_id"] == str(document_id)
        assert body[0]["score"] > body[1]["score"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_dense_search_respects_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "routers.retrieval._embedding_provider",
        _FakeEmbeddingProvider(vectors_by_text={"query": _vector(lead=0.0)}),
    )

    email = "endpoint-test-retrieval-owner-2@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        document_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/documents",
            files={"file": ("doc.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = uuid.UUID(document_response.json()["id"])

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            session.add_all(
                [
                    Chunk(
                        tenant_id=org_id,
                        document_id=document_id,
                        text=f"chunk {i}",
                        start=i,
                        end=i + 1,
                        index=i,
                        embedding=_vector(lead=float(i)),
                    )
                    for i in range(5)
                ]
            )
            await session.commit()

        response = client.post(
            _search_url(org_id, workspace_id, kb_id),
            json={"query": "query", "top_k": 2},
            headers=headers,
        )
        assert response.status_code == 200
        assert len(response.json()) == 2
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_dense_search_on_empty_knowledge_base_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "routers.retrieval._embedding_provider",
        _FakeEmbeddingProvider(vectors_by_text={"query": _vector(lead=0.0)}),
    )

    email = "endpoint-test-retrieval-owner-3@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _search_url(org_id, workspace_id, kb_id),
            json={"query": "query"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json() == []
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_dense_search_for_nonexistent_knowledge_base_returns_404() -> None:
    email = "endpoint-test-retrieval-owner-4@example.com"
    org_id, workspace_id, _kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _search_url(org_id, workspace_id, uuid.uuid4()),
            json={"query": "query"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


def test_dense_search_requires_auth() -> None:
    response = client.post(
        _search_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4()), json={"query": "query"}
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_end_user_role_cannot_search() -> None:
    """knowledge_base:read is org_owner/admin/manager only (verified
    against the real EXPECTED_ROLE_PERMISSIONS matrix in
    test_rbac_enforcement.py, not assumed) -- end_user only has
    workspace:read, same tier gap document:* endpoints already enforce."""
    owner_email = "endpoint-test-retrieval-owner-5@example.com"
    org_id, workspace_id, kb_id, owner_headers = _new_org_with_kb(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-retrieval-member@example.com",
            password="correct horse battery staple",
            full_name="Retrieval Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-retrieval-member@example.com")
            )
            member_user = result.scalar_one()
            role_result = await session.execute(select(Role).where(Role.name == "end_user"))
            end_user_role = role_result.scalar_one()
            await set_tenant_context(session, org_id)
            session.add(
                Membership(
                    tenant_id=org_id,
                    user_id=member_user.id,
                    workspace_id=None,
                    role_id=end_user_role.id,
                )
            )
            await session.commit()

        response = client.post(
            _search_url(org_id, workspace_id, kb_id),
            json={"query": "query"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-retrieval-member@example.com")
