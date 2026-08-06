"""Proves audit.py:write_audit_log() is actually wired into the routers,
through the real authenticated request path — not dependency_overrides,
now that real auth/RBAC exists (roadmap steps 070-072) and there's a
real end-to-end path to exercise instead.
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


@pytest.mark.anyio
async def test_organization_create_and_delete_are_audited() -> None:
    email = "endpoint-test-audit-org-owner@example.com"
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Audit Test"
    )
    headers = auth_headers(token)

    create_response = client.post(
        "/organizations",
        json={"name": "Audit Test Org", "slug": "endpoint-test-audit-org"},
        headers=headers,
    )
    org_id = uuid.UUID(create_response.json()["id"])

    async with get_session() as session:
        await set_tenant_context(session, org_id)
        result = await session.execute(
            select(AuditLog).where(AuditLog.resource_id == org_id).order_by(AuditLog.created_at)
        )
        logs = result.scalars().all()
        assert [log.action for log in logs] == ["organization.create"]
        assert logs[0].resource_type == "organization"
        assert logs[0].tenant_id == org_id
        assert logs[0].actor_user_id is not None

    client.delete(f"/organizations/{org_id}", headers=headers)

    async with get_session() as session:
        await set_tenant_context(session, org_id)
        result = await session.execute(
            select(AuditLog).where(AuditLog.resource_id == org_id).order_by(AuditLog.created_at)
        )
        logs = result.scalars().all()
        assert [log.action for log in logs] == ["organization.create", "organization.delete"]

        # Org itself and its membership are already gone (delete route
        # cascades); only the audit trail remains, which is the point
        # (audit_log.py's docstring: it should outlive the thing it's
        # about) — clean it up explicitly since it has no FK to cascade
        # from.
        for log in logs:
            await session.delete(log)
        await session.commit()

    await _cleanup_user(email)


@pytest.mark.anyio
async def test_workspace_create_is_audited() -> None:
    email = "endpoint-test-ws-audit-owner@example.com"
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="WS Audit Test"
    )
    headers = auth_headers(token)

    org_response = client.post(
        "/organizations",
        json={"name": "WS Audit Test Org", "slug": "endpoint-test-ws-audit-org"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])

    try:
        create_response = client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Audited WS", "slug": "endpoint-test-audited-ws"},
            headers=headers,
        )
        workspace_id = uuid.UUID(create_response.json()["id"])

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(AuditLog).where(AuditLog.resource_id == workspace_id)
            )
            logs = result.scalars().all()
            assert [log.action for log in logs] == ["workspace.create"]
            assert logs[0].tenant_id == org_id
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
