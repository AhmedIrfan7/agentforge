"""Integration tests against the real FastAPI app for routers/workspace.py.

Workspace routes now live under /organizations/{organization_id}/workspaces
and require a real access token + membership in that org (roadmap steps
070-072) — this used to test dependencies/tenant.py's NotImplementedError
placeholder via dependency_overrides; now there's a real end-to-end path
to exercise instead, which is a strictly stronger test.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.membership import Membership
from models.organization import Organization
from models.session import Session
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Workspace, AuditLog, Membership):
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


async def _new_org(email: str) -> tuple[uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Workspace Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Workspace Endpoint Test Org", "slug": f"endpoint-test-ws-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


def test_workspace_routes_require_auth() -> None:
    # A random org_id is fine here — auth is checked before anything else.
    response = client.get(
        f"/organizations/{uuid.uuid4()}/workspaces",
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_non_member_cannot_access_workspaces() -> None:
    org_id, _owner_headers = await _new_org("endpoint-test-ws-owner-1@example.com")
    try:
        outsider_token = signup_and_login(
            client,
            email="endpoint-test-ws-outsider@example.com",
            password="correct horse battery staple",
            full_name="Outsider",
        )
        response = client.get(
            f"/organizations/{org_id}/workspaces", headers=auth_headers(outsider_token)
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user("endpoint-test-ws-owner-1@example.com")
        await _cleanup_user("endpoint-test-ws-outsider@example.com")


@pytest.mark.anyio
async def test_workspace_crud_as_org_owner() -> None:
    email = "endpoint-test-ws-owner-2@example.com"
    org_id, headers = await _new_org(email)
    try:
        create_response = client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Endpoint WS", "slug": "endpoint-test-ws"},
            headers=headers,
        )
        assert create_response.status_code == 201
        workspace_id = create_response.json()["id"]
        assert create_response.json()["tenant_id"] == str(org_id)

        get_response = client.get(
            f"/organizations/{org_id}/workspaces/{workspace_id}", headers=headers
        )
        assert get_response.status_code == 200

        list_response = client.get(f"/organizations/{org_id}/workspaces", headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        delete_response = client.delete(
            f"/organizations/{org_id}/workspaces/{workspace_id}", headers=headers
        )
        assert delete_response.status_code == 204

        after_delete = client.get(
            f"/organizations/{org_id}/workspaces/{workspace_id}", headers=headers
        )
        assert after_delete.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_create_workspace() -> None:
    """end_user only has workspace:read (migration 1d0ef14faf9e) — proves
    require_permission actually distinguishes roles, not just membership."""
    owner_email = "endpoint-test-ws-owner-3@example.com"
    org_id, owner_headers = await _new_org(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-ws-member@example.com",
            password="correct horse battery staple",
            full_name="End User Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-ws-member@example.com")
            )
            member_user = result.scalar_one()

            from models.role import Role

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
            f"/organizations/{org_id}/workspaces",
            json={"name": "Should Fail", "slug": "endpoint-test-ws-should-fail"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403

        # But reading is fine — end_user has workspace:read.
        list_response = client.get(
            f"/organizations/{org_id}/workspaces", headers=auth_headers(member_token)
        )
        assert list_response.status_code == 200
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-ws-member@example.com")
