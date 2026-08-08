"""Integration tests against the real FastAPI app for
routers/knowledge_base.py (roadmap step 082).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.knowledge_base import KnowledgeBase
from models.membership import Membership
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
        for model in (KnowledgeBase, Workspace, AuditLog, Membership):
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


def _new_org_with_workspace(email: str) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="KB Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "KB Test Org", "slug": f"endpoint-test-kb-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "KB Test Workspace", "slug": "endpoint-test-kb-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    return org_id, workspace_id, headers


def _kb_url(org_id: uuid.UUID, workspace_id: uuid.UUID, suffix: str = "") -> str:
    return f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases{suffix}"


def test_knowledge_base_routes_require_auth() -> None:
    response = client.get(_kb_url(uuid.uuid4(), uuid.uuid4()))
    assert response.status_code == 401


@pytest.mark.anyio
async def test_non_member_cannot_access_knowledge_bases() -> None:
    org_id, workspace_id, _owner_headers = _new_org_with_workspace(
        "endpoint-test-kb-owner-1@example.com"
    )
    try:
        outsider_token = signup_and_login(
            client,
            email="endpoint-test-kb-outsider@example.com",
            password="correct horse battery staple",
            full_name="Outsider",
        )
        response = client.get(_kb_url(org_id, workspace_id), headers=auth_headers(outsider_token))
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user("endpoint-test-kb-owner-1@example.com")
        await _cleanup_user("endpoint-test-kb-outsider@example.com")


@pytest.mark.anyio
async def test_knowledge_base_crud_as_org_owner() -> None:
    email = "endpoint-test-kb-owner-2@example.com"
    org_id, workspace_id, headers = _new_org_with_workspace(email)
    try:
        create_response = client.post(
            _kb_url(org_id, workspace_id),
            json={"name": "Endpoint KB", "slug": "endpoint-test-kb", "description": "Docs"},
            headers=headers,
        )
        assert create_response.status_code == 201
        body = create_response.json()
        kb_id = body["id"]
        assert body["tenant_id"] == str(org_id)
        assert body["workspace_id"] == str(workspace_id)
        assert body["description"] == "Docs"

        get_response = client.get(_kb_url(org_id, workspace_id, f"/{kb_id}"), headers=headers)
        assert get_response.status_code == 200

        list_response = client.get(_kb_url(org_id, workspace_id), headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        delete_response = client.delete(_kb_url(org_id, workspace_id, f"/{kb_id}"), headers=headers)
        assert delete_response.status_code == 204

        after_delete = client.get(_kb_url(org_id, workspace_id, f"/{kb_id}"), headers=headers)
        assert after_delete.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_create_knowledge_base() -> None:
    owner_email = "endpoint-test-kb-owner-3@example.com"
    org_id, workspace_id, _owner_headers = _new_org_with_workspace(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-kb-member@example.com",
            password="correct horse battery staple",
            full_name="End User Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-kb-member@example.com")
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
            _kb_url(org_id, workspace_id),
            json={"name": "Should Fail", "slug": "endpoint-test-kb-should-fail"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-kb-member@example.com")


@pytest.mark.anyio
async def test_knowledge_base_not_visible_under_a_different_workspace() -> None:
    email = "endpoint-test-kb-owner-4@example.com"
    org_id, workspace_id, headers = _new_org_with_workspace(email)
    try:
        create_response = client.post(
            _kb_url(org_id, workspace_id),
            json={"name": "Scoped KB", "slug": "endpoint-test-kb-scoped"},
            headers=headers,
        )
        kb_id = create_response.json()["id"]

        other_ws_response = client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Other Workspace", "slug": "endpoint-test-kb-other-ws"},
            headers=headers,
        )
        other_workspace_id = uuid.UUID(other_ws_response.json()["id"])

        # Real knowledge base, real org, real membership -- just the
        # wrong workspace in the URL. Must 404, not leak across
        # workspaces within the same organization.
        response = client.get(_kb_url(org_id, other_workspace_id, f"/{kb_id}"), headers=headers)
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_duplicate_slug_within_workspace_conflicts_but_other_workspace_ok() -> None:
    email = "endpoint-test-kb-owner-5@example.com"
    org_id, workspace_id, headers = _new_org_with_workspace(email)
    try:
        first = client.post(
            _kb_url(org_id, workspace_id),
            json={"name": "First", "slug": "endpoint-test-kb-dup"},
            headers=headers,
        )
        assert first.status_code == 201

        duplicate = client.post(
            _kb_url(org_id, workspace_id),
            json={"name": "Second", "slug": "endpoint-test-kb-dup"},
            headers=headers,
        )
        assert duplicate.status_code == 409

        other_ws_response = client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Sibling Workspace", "slug": "endpoint-test-kb-sibling-ws"},
            headers=headers,
        )
        other_workspace_id = uuid.UUID(other_ws_response.json()["id"])

        same_slug_other_workspace = client.post(
            _kb_url(org_id, other_workspace_id),
            json={"name": "Same Slug Elsewhere", "slug": "endpoint-test-kb-dup"},
            headers=headers,
        )
        assert same_slug_other_workspace.status_code == 201
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_workspace_from_wrong_organization_returns_404() -> None:
    email_a = "endpoint-test-kb-orga@example.com"
    email_b = "endpoint-test-kb-orgb@example.com"
    org_a_id, workspace_a_id, _headers_a = _new_org_with_workspace(email_a)
    org_b_id, _workspace_b_id, headers_b = _new_org_with_workspace(email_b)
    try:
        # headers_b's caller is a real member of org_b, but workspace_a_id
        # belongs to org_a -- must 404, not treat org_b's membership as
        # sufficient to reach into a different organization's workspace.
        response = client.post(
            _kb_url(org_b_id, workspace_a_id),
            json={"name": "Cross Org", "slug": "endpoint-test-kb-cross-org"},
            headers=headers_b,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_a_id)
        await _cleanup_org(org_b_id)
        await _cleanup_user(email_a)
        await _cleanup_user(email_b)
