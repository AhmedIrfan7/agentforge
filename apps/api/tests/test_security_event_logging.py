"""Tests for the three real security events roadmap step 255 names by
name (AGENTS.md's own "AUDIT LOGGING" section): failed logins,
permission denials, cross-tenant attempts.

Permission denials and cross-tenant attempts both have a real tenant_id
available at the point of failure, so they write real AuditLog rows
(dependencies/rbac.py, dependencies/tenant.py) -- queryable through the
same real audit-log viewer step 247 already built. A failed login has
no tenant context yet (the caller hasn't proven who they are), so it
logs a real structured event instead (routers/auth.py) -- see that
module's own docstring for why AuditLog doesn't fit there.
"""

import uuid

import pytest
import structlog.testing
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
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


def _new_org(email: str, slug: str) -> tuple[uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client,
        email=email,
        password="correct horse battery staple",
        full_name="Security Event Test",
    )
    headers = auth_headers(token)
    org_response = client.post(
        "/organizations",
        json={"name": "Security Event Test Org", "slug": slug},
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
        for model in (AuditLog, Membership):
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
async def test_permission_denial_writes_a_real_audit_log_row() -> None:
    owner_email = "endpoint-test-security-perm-owner@example.com"
    end_user_email = "endpoint-test-security-perm-end-user@example.com"
    org_id, _owner_headers = _new_org(owner_email, "endpoint-test-security-perm-org")
    try:
        end_user_headers = await _add_member_with_role(org_id, end_user_email, "end_user")

        response = client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Denied WS", "slug": "endpoint-test-security-perm-ws"},
            headers=end_user_headers,
        )
        assert response.status_code == 403

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(AuditLog).where(AuditLog.action == "security.permission_denied")
            )
            logs = result.scalars().all()
            assert len(logs) == 1
            assert logs[0].resource_type == "user"
            assert logs[0].extra == {"permission_key": "workspace:create"}
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(end_user_email)


@pytest.mark.anyio
async def test_cross_tenant_attempt_writes_a_real_audit_log_row_on_the_targeted_org() -> None:
    org_a_email = "endpoint-test-security-cross-a@example.com"
    org_b_email = "endpoint-test-security-cross-b@example.com"
    org_a_id, org_a_headers = _new_org(org_a_email, "endpoint-test-security-cross-org-a")
    org_b_id, _org_b_headers = _new_org(org_b_email, "endpoint-test-security-cross-org-b")
    try:
        # org A's own real, authenticated user tries to reach org B's
        # workspaces using their own real token -- no membership there.
        response = client.get(f"/organizations/{org_b_id}/workspaces", headers=org_a_headers)
        assert response.status_code == 403

        async with get_session() as session:
            await set_tenant_context(session, org_b_id)
            result = await session.execute(
                select(AuditLog).where(AuditLog.action == "security.cross_tenant_attempt")
            )
            logs = result.scalars().all()
            assert len(logs) == 1
            assert logs[0].tenant_id == org_b_id
            assert logs[0].resource_id == org_b_id
    finally:
        await _cleanup_org(org_a_id)
        await _cleanup_org(org_b_id)
        await _cleanup_user(org_a_email)
        await _cleanup_user(org_b_email)


@pytest.mark.anyio
async def test_failed_login_with_wrong_password_logs_a_structured_event() -> None:
    email = "endpoint-test-security-login-wrong-pw@example.com"
    signup_and_login(client, email=email, password="correct horse battery staple", full_name="Test")
    try:
        with structlog.testing.capture_logs() as logs:
            response = client.post(
                "/auth/login", json={"email": email, "password": "definitely wrong"}
            )
        assert response.status_code == 401
        matching = [log for log in logs if log.get("event") == "login_failed"]
        assert len(matching) == 1
        assert matching[0]["email"] == email
    finally:
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_failed_login_with_nonexistent_user_logs_a_structured_event() -> None:
    email = "endpoint-test-security-login-no-such-user@example.com"
    with structlog.testing.capture_logs() as logs:
        response = client.post("/auth/login", json={"email": email, "password": "x"})
    assert response.status_code == 401
    matching = [log for log in logs if log.get("event") == "login_failed"]
    assert len(matching) == 1
    assert matching[0]["email"] == email
