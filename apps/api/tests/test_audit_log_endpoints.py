"""Integration tests against the real FastAPI app for routers/audit_log.py
(roadmap step 247) -- the first real reader of the AuditLog rows every
router has been writing since step 072.
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
from models.role import Role
from models.session import Session
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


def _new_org(email: str) -> tuple[uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Audit Log Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Audit Log Test Org", "slug": f"endpoint-test-audit-log-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


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


@pytest.mark.anyio
async def test_owner_can_list_real_audit_logs_newest_first() -> None:
    email = "endpoint-test-audit-log-owner-1@example.com"
    org_id, headers = _new_org(email)
    try:
        # org.create already happened above; workspace.create adds a
        # second, later row for the same real request path.
        client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Audit Log WS", "slug": "endpoint-test-audit-log-ws"},
            headers=headers,
        )

        response = client.get(f"/organizations/{org_id}/audit-logs", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        actions = [item["action"] for item in body["items"]]
        assert actions == ["workspace.create", "organization.create"]
        assert body["items"][0]["actor_email"] == email
        assert body["items"][0]["resource_type"] == "workspace"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_filters_by_action_and_resource_type() -> None:
    email = "endpoint-test-audit-log-owner-2@example.com"
    org_id, headers = _new_org(email)
    try:
        client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Audit Log WS 2", "slug": "endpoint-test-audit-log-ws-2"},
            headers=headers,
        )

        by_action = client.get(
            f"/organizations/{org_id}/audit-logs",
            params={"action": "workspace.create"},
            headers=headers,
        )
        assert by_action.status_code == 200
        assert [item["action"] for item in by_action.json()["items"]] == ["workspace.create"]

        by_resource_type = client.get(
            f"/organizations/{org_id}/audit-logs",
            params={"resource_type": "organization"},
            headers=headers,
        )
        assert by_resource_type.status_code == 200
        assert [item["resource_type"] for item in by_resource_type.json()["items"]] == [
            "organization"
        ]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_pagination_limit_and_offset() -> None:
    email = "endpoint-test-audit-log-owner-3@example.com"
    org_id, headers = _new_org(email)
    try:
        client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Audit Log WS 3", "slug": "endpoint-test-audit-log-ws-3"},
            headers=headers,
        )

        page1 = client.get(
            f"/organizations/{org_id}/audit-logs",
            params={"limit": 1, "offset": 0},
            headers=headers,
        )
        page2 = client.get(
            f"/organizations/{org_id}/audit-logs",
            params={"limit": 1, "offset": 1},
            headers=headers,
        )
        assert page1.json()["total"] == 2
        assert page2.json()["total"] == 2
        assert len(page1.json()["items"]) == 1
        assert len(page2.json()["items"]) == 1
        assert page1.json()["items"][0]["id"] != page2.json()["items"][0]["id"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_manager_role_cannot_read_audit_logs() -> None:
    email = "endpoint-test-audit-log-owner-4@example.com"
    org_id, headers = _new_org(email)
    manager_email = "endpoint-test-audit-log-manager-4@example.com"
    try:
        manager_headers = await _add_member_with_role(org_id, manager_email, "manager")

        response = client.get(f"/organizations/{org_id}/audit-logs", headers=manager_headers)
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
        await _cleanup_user(manager_email)


@pytest.mark.anyio
async def test_admin_role_can_read_audit_logs() -> None:
    email = "endpoint-test-audit-log-owner-5@example.com"
    org_id, headers = _new_org(email)
    admin_email = "endpoint-test-audit-log-admin-5@example.com"
    try:
        admin_headers = await _add_member_with_role(org_id, admin_email, "admin")

        response = client.get(f"/organizations/{org_id}/audit-logs", headers=admin_headers)
        assert response.status_code == 200
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
        await _cleanup_user(admin_email)
