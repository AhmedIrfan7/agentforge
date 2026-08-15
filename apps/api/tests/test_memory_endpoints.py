"""Integration tests against the real FastAPI app for
routers/memory.py (roadmap step 169).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.membership import Membership
from models.memory import Memory
from models.organization import Organization
from models.session import Session
from models.user import User
from models.workspace import Workspace
from repositories.memory import MemoryRepository
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Memory, Workspace, AuditLog, Membership):
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
        client, email=email, password="correct horse battery staple", full_name="Memory Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Memory Test Org", "slug": f"endpoint-test-mem-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    return org_id, headers


async def _user_id_for(email: str) -> uuid.UUID:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one().id


async def _new_bare_user(email: str) -> uuid.UUID:
    """A real User row with no membership/org of its own -- just enough
    for a real FK target (Memory.user_id) in "someone else's memory"
    tests. Not created via /auth/signup since these tests don't need a
    real login for this user, only a real id to reference."""
    async with get_session() as session:
        user = User(email=email, full_name="Someone Else")
        session.add(user)
        await session.flush()
        await session.commit()
        return user.id


def _memory_url(org_id: uuid.UUID, suffix: str = "") -> str:
    return f"/organizations/{org_id}/memory{suffix}"


async def _seed_memory(
    tenant_id: uuid.UUID,
    *,
    scope: str,
    content: str,
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        memory = await repo.create(
            scope=scope, user_id=user_id, content=content, importance_score=0.7
        )
        await session.commit()
        return memory.id


def test_memory_routes_require_auth() -> None:
    response = client.get(_memory_url(uuid.uuid4()))
    assert response.status_code == 401


@pytest.mark.anyio
async def test_list_my_memory_returns_only_my_own_user_scoped_memories() -> None:
    email = "endpoint-test-mem-owner-1@example.com"
    other_email = "endpoint-test-mem-other-1@example.com"
    org_id, headers = _new_org(email)
    user_id = await _user_id_for(email)
    other_user_id = await _new_bare_user(other_email)
    try:
        await _seed_memory(org_id, scope="user", user_id=user_id, content="mine")
        await _seed_memory(org_id, scope="organization", content="org-wide, not mine")
        await _seed_memory(org_id, scope="user", user_id=other_user_id, content="not mine")

        response = client.get(_memory_url(org_id), headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert [item["content"] for item in body["items"]] == ["mine"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
        await _cleanup_user(other_email)


@pytest.mark.anyio
async def test_export_my_memory_returns_everything_without_pagination() -> None:
    email = "endpoint-test-mem-owner-2@example.com"
    org_id, headers = _new_org(email)
    user_id = await _user_id_for(email)
    try:
        for i in range(3):
            await _seed_memory(org_id, scope="user", user_id=user_id, content=f"memory-{i}")

        response = client.get(_memory_url(org_id, "/export"), headers=headers)

        assert response.status_code == 200
        assert len(response.json()) == 3
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_delete_my_memory_removes_it() -> None:
    email = "endpoint-test-mem-owner-3@example.com"
    org_id, headers = _new_org(email)
    user_id = await _user_id_for(email)
    try:
        memory_id = await _seed_memory(org_id, scope="user", user_id=user_id, content="delete me")

        delete_response = client.delete(_memory_url(org_id, f"/{memory_id}"), headers=headers)
        assert delete_response.status_code == 204

        list_response = client.get(_memory_url(org_id), headers=headers)
        assert list_response.json()["total"] == 0
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_cannot_delete_another_users_memory() -> None:
    email = "endpoint-test-mem-owner-4@example.com"
    other_email = "endpoint-test-mem-other-4@example.com"
    org_id, headers = _new_org(email)
    other_user_id = await _new_bare_user(other_email)
    try:
        memory_id = await _seed_memory(
            org_id, scope="user", user_id=other_user_id, content="not yours"
        )

        response = client.delete(_memory_url(org_id, f"/{memory_id}"), headers=headers)

        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
        await _cleanup_user(other_email)


@pytest.mark.anyio
async def test_non_member_cannot_access_memory_endpoints() -> None:
    org_id, _owner_headers = _new_org("endpoint-test-mem-owner-5@example.com")
    try:
        outsider_token = signup_and_login(
            client,
            email="endpoint-test-mem-outsider@example.com",
            password="correct horse battery staple",
            full_name="Outsider",
        )
        response = client.get(_memory_url(org_id), headers=auth_headers(outsider_token))
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user("endpoint-test-mem-owner-5@example.com")
        await _cleanup_user("endpoint-test-mem-outsider@example.com")
