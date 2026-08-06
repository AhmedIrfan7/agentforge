"""Integration tests against the real FastAPI app for routers/workspace.py.

Workspace routes depend on get_current_tenant_id, which raises
NotImplementedError until Milestone 2's auth exists (dependencies/tenant.py)
— so most of this file proves that failure mode is honest (500, no data
leak) by default, then overrides the dependency the same way real auth
eventually will to prove the routes themselves are correctly wired.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from dependencies.tenant import get_current_tenant_id
from main import app
from models.organization import Organization
from models.workspace import Workspace

client = TestClient(app)


def test_workspace_routes_fail_closed_without_auth() -> None:
    # raise_server_exceptions=False: without it, TestClient re-raises the
    # NotImplementedError into the test instead of returning the 500
    # response errors.py's handler actually produces (matches the real
    # behavior verified live against uvicorn — see the step 047-052
    # commit message). Same thing tests/test_tenant_dependency.py hit.
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    response = no_raise_client.get("/workspaces")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


@pytest.mark.anyio
async def test_workspace_crud_with_resolved_tenant() -> None:
    async with get_session() as session:
        org = Organization(name="Workspace Endpoint Test Org", slug="endpoint-test-ws-org")
        session.add(org)
        await session.commit()

    async def fake_tenant() -> uuid.UUID:
        return org.id

    app.dependency_overrides[get_current_tenant_id] = fake_tenant
    try:
        create_response = client.post(
            "/workspaces", json={"name": "Endpoint WS", "slug": "endpoint-test-ws"}
        )
        assert create_response.status_code == 201
        workspace_id = create_response.json()["id"]
        assert create_response.json()["tenant_id"] == str(org.id)

        get_response = client.get(f"/workspaces/{workspace_id}")
        assert get_response.status_code == 200

        list_response = client.get("/workspaces")
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        delete_response = client.delete(f"/workspaces/{workspace_id}")
        assert delete_response.status_code == 204

        after_delete = client.get(f"/workspaces/{workspace_id}")
        assert after_delete.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_tenant_id, None)
        async with get_session() as cleanup_session:
            await set_tenant_context(cleanup_session, org.id)
            result = await cleanup_session.execute(
                select(Workspace).where(Workspace.tenant_id == org.id)
            )
            for ws in result.scalars().all():
                await cleanup_session.delete(ws)
            await cleanup_session.delete(await cleanup_session.get(Organization, org.id))
            await cleanup_session.commit()
