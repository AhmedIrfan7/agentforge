import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from dependencies.tenant import get_current_tenant_id
from main import app
from models.audit_log import AuditLog
from models.organization import Organization

client = TestClient(app)


@pytest.mark.anyio
async def test_organization_create_and_delete_are_audited() -> None:
    create_response = client.post(
        "/organizations", json={"name": "Audit Test Org", "slug": "endpoint-test-audit-org"}
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

    client.delete(f"/organizations/{org_id}")

    async with get_session() as session:
        await set_tenant_context(session, org_id)
        result = await session.execute(
            select(AuditLog).where(AuditLog.resource_id == org_id).order_by(AuditLog.created_at)
        )
        logs = result.scalars().all()
        assert [log.action for log in logs] == ["organization.create", "organization.delete"]

        # Cleanup — org itself is already gone; only the audit trail remains,
        # which is the point (audit_log.py's docstring: it should outlive
        # the thing it's about). Clean it up explicitly since it has no FK
        # to cascade from.
        for log in logs:
            await session.delete(log)
        await session.commit()


@pytest.mark.anyio
async def test_workspace_create_is_audited() -> None:
    async with get_session() as setup_session:
        org = Organization(name="WS Audit Test Org", slug="endpoint-test-ws-audit-org")
        setup_session.add(org)
        await setup_session.commit()

    async def fake_tenant() -> uuid.UUID:
        return org.id

    app.dependency_overrides[get_current_tenant_id] = fake_tenant
    try:
        create_response = client.post(
            "/workspaces", json={"name": "Audited WS", "slug": "endpoint-test-audited-ws"}
        )
        workspace_id = uuid.UUID(create_response.json()["id"])

        async with get_session() as session:
            await set_tenant_context(session, org.id)
            result = await session.execute(
                select(AuditLog).where(AuditLog.resource_id == workspace_id)
            )
            logs = result.scalars().all()
            assert [log.action for log in logs] == ["workspace.create"]
            assert logs[0].tenant_id == org.id
    finally:
        app.dependency_overrides.pop(get_current_tenant_id, None)
        async with get_session() as cleanup_session:
            await set_tenant_context(cleanup_session, org.id)
            from models.workspace import Workspace

            ws_result = await cleanup_session.execute(
                select(Workspace).where(Workspace.tenant_id == org.id)
            )
            for ws in ws_result.scalars().all():
                await cleanup_session.delete(ws)
            log_result = await cleanup_session.execute(
                select(AuditLog).where(AuditLog.tenant_id == org.id)
            )
            for log in log_result.scalars().all():
                await cleanup_session.delete(log)
            await cleanup_session.delete(await cleanup_session.get(Organization, org.id))
            await cleanup_session.commit()
