"""Integration tests against the real FastAPI app (main.app), not a
throwaway test app — these exercise routers/organization.py, errors.py,
and schemas/organization.py together the way real HTTP traffic will.

Every test here is async (@pytest.mark.anyio), even though TestClient
itself is synchronous — mixing an async autouse fixture with sync test
functions triggers a real pytest/anyio fixture-teardown-ordering bug
("assert not self._finalizers") in this pytest 9.1.1 / anyio 4.14.2
combination. Keeping the whole file consistently async avoids it.
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session
from main import app
from models.organization import Organization

client = TestClient(app)


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        result = await session.execute(
            select(Organization).where(Organization.slug.like("endpoint-test-%"))
        )
        for org in result.scalars().all():
            await session.delete(org)
        await session.commit()


@pytest.mark.anyio
async def test_create_organization() -> None:
    response = client.post(
        "/organizations", json={"name": "Endpoint Test Org", "slug": "endpoint-test-create"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Endpoint Test Org"
    assert body["slug"] == "endpoint-test-create"
    assert "id" in body


@pytest.mark.anyio
async def test_create_duplicate_slug_returns_409() -> None:
    client.post("/organizations", json={"name": "First", "slug": "endpoint-test-dup"})
    response = client.post("/organizations", json={"name": "Second", "slug": "endpoint-test-dup"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


@pytest.mark.anyio
async def test_create_with_invalid_slug_returns_422() -> None:
    response = client.post("/organizations", json={"name": "Bad Slug", "slug": "Not A Valid Slug!"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.anyio
async def test_get_nonexistent_organization_returns_404() -> None:
    response = client.get("/organizations/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.anyio
async def test_get_and_delete_organization() -> None:
    create_response = client.post(
        "/organizations", json={"name": "Get Delete Test", "slug": "endpoint-test-get-delete"}
    )
    org_id = create_response.json()["id"]

    get_response = client.get(f"/organizations/{org_id}")
    assert get_response.status_code == 200
    assert get_response.json()["slug"] == "endpoint-test-get-delete"

    delete_response = client.delete(f"/organizations/{org_id}")
    assert delete_response.status_code == 204

    after_delete = client.get(f"/organizations/{org_id}")
    assert after_delete.status_code == 404


@pytest.mark.anyio
async def test_list_organizations_is_paginated() -> None:
    for i in range(3):
        client.post(
            "/organizations", json={"name": f"List Test {i}", "slug": f"endpoint-test-list-{i}"}
        )

    response = client.get("/organizations", params={"limit": 2, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) <= 2
    assert body["total"] >= 3
