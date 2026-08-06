"""Proves dependencies/tenant.py works end-to-end through FastAPI's actual
dependency-injection chain, not just db.set_tenant_context() called
directly (that's already covered by tests/test_tenant_isolation.py).
No real routes use get_tenant_db yet (those start at roadmap step 047),
so this builds a minimal throwaway route to exercise the dependency the
same way a real one eventually will.
"""

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, set_tenant_context
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from models.organization import Organization
from models.workspace import Workspace


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/test/workspaces")
    async def list_workspaces(session: AsyncSession = Depends(get_tenant_db)) -> list[str]:
        result = await session.execute(select(Workspace.slug))
        return [row[0] for row in result.all()]

    return app


def test_unresolved_tenant_dependency_fails_closed() -> None:
    app = _build_test_app()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/test/workspaces")

    assert response.status_code == 500


@pytest.mark.anyio
async def test_overridden_tenant_resolution_enforces_rls_end_to_end() -> None:
    # Unlike the other tests in this suite, this one has to commit: the
    # TestClient-driven request opens its own DB connection (via
    # get_tenant_db's own get_session() call), separate from this
    # function's — an uncommitted transaction here would simply be
    # invisible to it. Explicit cleanup in `finally` instead.
    async with get_session() as setup_session:
        org_a = Organization(name="Dep Test Org A", slug="dep-test-org-a")
        org_b = Organization(name="Dep Test Org B", slug="dep-test-org-b")
        setup_session.add_all([org_a, org_b])
        await setup_session.flush()

        await set_tenant_context(setup_session, org_a.id)
        workspace_a = Workspace(tenant_id=org_a.id, name="A Workspace", slug="dep-test-a-ws")
        setup_session.add(workspace_a)
        await setup_session.commit()

    try:
        app = _build_test_app()

        async def fake_resolve_tenant_a() -> uuid.UUID:
            return org_a.id

        async def fake_resolve_tenant_b() -> uuid.UUID:
            return org_b.id

        client = TestClient(app)

        app.dependency_overrides[get_current_tenant_id] = fake_resolve_tenant_a
        response = client.get("/test/workspaces")
        assert response.status_code == 200
        assert response.json() == ["dep-test-a-ws"]

        app.dependency_overrides[get_current_tenant_id] = fake_resolve_tenant_b
        response = client.get("/test/workspaces")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        async with get_session() as cleanup_session:
            await set_tenant_context(cleanup_session, org_a.id)
            await cleanup_session.delete(await cleanup_session.get(Workspace, workspace_a.id))
            await cleanup_session.delete(await cleanup_session.get(Organization, org_a.id))
            await cleanup_session.delete(await cleanup_session.get(Organization, org_b.id))
            await cleanup_session.commit()
