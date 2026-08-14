"""Integration tests against the real FastAPI app for
routers/retrieval.py (roadmap steps 120-122: dense, keyword, hybrid).

Real org/workspace/knowledge-base/document setup through the real HTTP
endpoints, real Chunk rows with real embeddings added directly via the
ORM (no live worker needed -- matches the chunk-injection pattern
test_document_endpoints.py's own delete test already established), and
routers.retrieval._retriever_agent's own embedding_provider (agents/
retriever.py, step 124) swapped for a fake so this can prove real
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


def _keyword_search_url(org_id: uuid.UUID, workspace_id: uuid.UUID, kb_id: uuid.UUID) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/search/keyword"
    )


def _hybrid_search_url(org_id: uuid.UUID, workspace_id: uuid.UUID, kb_id: uuid.UUID) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/search/hybrid"
    )


@pytest.mark.anyio
async def test_dense_search_returns_the_closest_chunk_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "routers.retrieval._retriever_agent._embedding_provider",
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
        "routers.retrieval._retriever_agent._embedding_provider",
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
        "routers.retrieval._retriever_agent._embedding_provider",
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


@pytest.mark.anyio
async def test_keyword_search_returns_matching_chunk() -> None:
    """No fake provider needed here, unlike dense search -- keyword
    search has no embedding step, so this works for real in every
    environment including one with no OPENAI_API_KEY."""
    email = "endpoint-test-retrieval-owner-6@example.com"
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
                        text="Our refund policy allows returns within thirty days.",
                        start=0,
                        end=1,
                        index=0,
                    ),
                    Chunk(
                        tenant_id=org_id,
                        document_id=document_id,
                        text="The quick brown fox jumps over the lazy dog.",
                        start=1,
                        end=2,
                        index=1,
                    ),
                ]
            )
            await session.commit()

        response = client.post(
            _keyword_search_url(org_id, workspace_id, kb_id),
            json={"query": "refund policy"},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert "refund policy" in body[0]["text"]
        assert body[0]["document_id"] == str(document_id)
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_keyword_search_with_no_matches_returns_empty_list() -> None:
    email = "endpoint-test-retrieval-owner-7@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _keyword_search_url(org_id, workspace_id, kb_id),
            json={"query": "nothing matches this"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json() == []
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_keyword_search_for_nonexistent_knowledge_base_returns_404() -> None:
    email = "endpoint-test-retrieval-owner-8@example.com"
    org_id, workspace_id, _kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _keyword_search_url(org_id, workspace_id, uuid.uuid4()),
            json={"query": "query"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_keyword_search() -> None:
    owner_email = "endpoint-test-retrieval-owner-9@example.com"
    org_id, workspace_id, kb_id, owner_headers = _new_org_with_kb(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-retrieval-kw-member@example.com",
            password="correct horse battery staple",
            full_name="Retrieval KW Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-retrieval-kw-member@example.com")
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
            _keyword_search_url(org_id, workspace_id, kb_id),
            json={"query": "query"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-retrieval-kw-member@example.com")
        await _cleanup_user("endpoint-test-retrieval-member@example.com")


@pytest.mark.anyio
async def test_hybrid_search_ranks_a_chunk_matching_both_signals_above_one_matching_only_dense(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real point of hybrid search: a chunk present in BOTH the
    dense and keyword result lists should outrank one that only
    appears in dense, even when that dense-only chunk ranks a close
    second on cosine similarity alone -- proves retrieval_fusion.py's
    RRF is actually driving the endpoint's real ranking, not just that
    both underlying calls happen."""
    monkeypatch.setattr(
        "routers.retrieval._retriever_agent._embedding_provider",
        _FakeEmbeddingProvider(vectors_by_text={"refund policy": _vector(lead=1.0)}),
    )

    email = "endpoint-test-retrieval-owner-10@example.com"
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
                        text="Our refund policy is generous",
                        start=0,
                        end=1,
                        index=0,
                        embedding=_vector(lead=1.0),
                    ),
                    Chunk(
                        tenant_id=org_id,
                        document_id=document_id,
                        text="The weather today is sunny and warm",
                        start=1,
                        end=2,
                        index=1,
                        embedding=_vector(lead=0.99),
                    ),
                ]
            )
            await session.commit()

        response = client.post(
            _hybrid_search_url(org_id, workspace_id, kb_id),
            json={"query": "refund policy", "top_k": 5},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["text"] == "Our refund policy is generous"
        assert body[0]["score"] > body[1]["score"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_hybrid_search_respects_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "routers.retrieval._retriever_agent._embedding_provider",
        _FakeEmbeddingProvider(vectors_by_text={"query": _vector(lead=0.0)}),
    )

    email = "endpoint-test-retrieval-owner-11@example.com"
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
                        text=f"query chunk {i}",
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
            _hybrid_search_url(org_id, workspace_id, kb_id),
            json={"query": "query", "top_k": 2},
            headers=headers,
        )
        assert response.status_code == 200
        assert len(response.json()) == 2
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_hybrid_search_on_empty_knowledge_base_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "routers.retrieval._retriever_agent._embedding_provider",
        _FakeEmbeddingProvider(vectors_by_text={"query": _vector(lead=0.0)}),
    )

    email = "endpoint-test-retrieval-owner-12@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _hybrid_search_url(org_id, workspace_id, kb_id),
            json={"query": "query"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json() == []
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_hybrid_search_for_nonexistent_knowledge_base_returns_404() -> None:
    email = "endpoint-test-retrieval-owner-13@example.com"
    org_id, workspace_id, _kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _hybrid_search_url(org_id, workspace_id, uuid.uuid4()),
            json={"query": "query"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_dense_search_document_id_filter_is_wired_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Roadmap step 123 -- filtering itself is proven directly against
    real Postgres in test_pgvector_store.py/test_chunk_repository_
    keyword_search.py; this only needs to prove SearchRequest.
    document_id actually reaches the real endpoint's real query, the
    same "prove the wiring, not re-derive the underlying logic"
    reasoning every other endpoint test in this file already uses."""
    monkeypatch.setattr(
        "routers.retrieval._retriever_agent._embedding_provider",
        _FakeEmbeddingProvider(vectors_by_text={"query": _vector(lead=1.0)}),
    )

    email = "endpoint-test-retrieval-owner-14@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        docs_url = (
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/documents"
        )
        first_response = client.post(
            docs_url, files={"file": ("first.txt", b"content", "text/plain")}, headers=headers
        )
        first_id = uuid.UUID(first_response.json()["id"])
        second_response = client.post(
            docs_url, files={"file": ("second.txt", b"content", "text/plain")}, headers=headers
        )
        second_id = uuid.UUID(second_response.json()["id"])

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            session.add_all(
                [
                    Chunk(
                        tenant_id=org_id,
                        document_id=first_id,
                        text="in first document",
                        start=0,
                        end=1,
                        index=0,
                        embedding=_vector(lead=1.0),
                    ),
                    Chunk(
                        tenant_id=org_id,
                        document_id=second_id,
                        text="in second document",
                        start=0,
                        end=1,
                        index=0,
                        embedding=_vector(lead=1.0),
                    ),
                ]
            )
            await session.commit()

        response = client.post(
            _search_url(org_id, workspace_id, kb_id),
            json={"query": "query", "document_id": str(first_id)},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert [r["text"] for r in body] == ["in first document"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


def _context_url(org_id: uuid.UUID, workspace_id: uuid.UUID, kb_id: uuid.UUID) -> str:
    return f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/context"


@pytest.mark.anyio
async def test_context_endpoint_returns_real_citations_for_keyword_strategy() -> None:
    """The polished endpoint (roadmap step 133) -- keyword strategy
    needs no OPENAI_API_KEY, so this proves the full real pipeline
    (retrieval -> context_builder -> citations) end to end without a
    fake embedding provider: document_title/knowledge_base_name come
    from real rows, section is parsed from the chunk's own real leading
    markdown heading."""
    email = "endpoint-test-context-owner-1@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        document_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/documents",
            files={"file": ("policy.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = uuid.UUID(document_response.json()["id"])

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            session.add(
                Chunk(
                    tenant_id=org_id,
                    document_id=document_id,
                    text="## Refund Policy\n\nOur refund policy allows returns.",
                    start=0,
                    end=1,
                    index=0,
                )
            )
            await session.commit()

        response = client.post(
            _context_url(org_id, workspace_id, kb_id),
            json={"query": "refund policy", "strategy": "keyword"},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["document_id"] == str(document_id)
        assert body[0]["document_title"] == "policy.txt"
        assert body[0]["knowledge_base_name"] == "Retrieval Test KB"
        assert body[0]["section"] == "Refund Policy"
        assert "refund policy" in body[0]["text"].lower()
        assert "score" not in body[0]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_context_endpoint_dense_strategy_is_wired_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "routers.retrieval._retriever_agent._embedding_provider",
        _FakeEmbeddingProvider(vectors_by_text={"refund": _vector(lead=1.0)}),
    )

    email = "endpoint-test-context-owner-2@example.com"
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
            session.add(
                Chunk(
                    tenant_id=org_id,
                    document_id=document_id,
                    text="a real chunk of text",
                    start=0,
                    end=1,
                    index=0,
                    embedding=_vector(lead=1.0),
                )
            )
            await session.commit()

        response = client.post(
            _context_url(org_id, workspace_id, kb_id),
            json={"query": "refund", "strategy": "dense"},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert [r["text"] for r in body] == ["a real chunk of text"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_context_endpoint_respects_the_token_budget() -> None:
    email = "endpoint-test-context-owner-3@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        document_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/documents",
            files={"file": ("doc.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = uuid.UUID(document_response.json()["id"])

        # Two chunks that both match "refund policy" on their own but
        # together exceed a small max_tokens budget.
        long_text = "refund policy " + " ".join(f"filler{i}" for i in range(200))
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            session.add_all(
                [
                    Chunk(
                        tenant_id=org_id,
                        document_id=document_id,
                        text=long_text,
                        start=0,
                        end=1,
                        index=0,
                    ),
                    Chunk(
                        tenant_id=org_id,
                        document_id=document_id,
                        text="refund policy short chunk",
                        start=1,
                        end=2,
                        index=1,
                    ),
                ]
            )
            await session.commit()

        response = client.post(
            _context_url(org_id, workspace_id, kb_id),
            json={"query": "refund policy", "strategy": "keyword", "max_tokens": 5},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) < 2
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_context_endpoint_rerank_and_multi_query_flags_do_not_error() -> None:
    """Proves the wiring, not re-derives rerank()/search_multi_query()'s
    own correctness -- both are already independently, rigorously
    tested at the agent layer (test_retriever_agent.py)."""
    email = "endpoint-test-context-owner-4@example.com"
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
            session.add(
                Chunk(
                    tenant_id=org_id,
                    document_id=document_id,
                    text="refund policy and shipping details",
                    start=0,
                    end=1,
                    index=0,
                )
            )
            await session.commit()

        response = client.post(
            _context_url(org_id, workspace_id, kb_id),
            json={
                "query": "refund policy and shipping",
                "strategy": "keyword",
                "rerank": True,
                "multi_query": True,
            },
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["text"] == "refund policy and shipping details"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_context_endpoint_for_nonexistent_knowledge_base_returns_404() -> None:
    email = "endpoint-test-context-owner-5@example.com"
    org_id, workspace_id, _kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _context_url(org_id, workspace_id, uuid.uuid4()),
            json={"query": "query"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
