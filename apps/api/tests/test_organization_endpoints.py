"""Integration tests against the real FastAPI app (main.app), not a
throwaway test app — these exercise routers/organization.py, errors.py,
and schemas/organization.py together the way real HTTP traffic will.

Every route here requires a real access token now (roadmap steps
070-072) — tests/helpers.py:signup_and_login() gets one through the
actual signup/login endpoints, not a mock.

Every test here is async (@pytest.mark.anyio), even though TestClient
itself is synchronous — mixing an async autouse fixture with sync test
functions triggers a real pytest/anyio fixture-teardown-ordering bug
("assert not self._finalizers") in this pytest 9.1.1 / anyio 4.14.2
combination. Keeping the whole file consistently async avoids it.
"""

import uuid
from collections.abc import AsyncGenerator

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
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


@pytest.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None]:
    yield
    async with get_session() as session:
        org_result = await session.execute(
            select(Organization).where(Organization.slug.like("endpoint-test-%"))
        )
        for org in org_result.scalars().all():
            # See the long comment history on this pattern: audit_logs and
            # memberships both have no FK cascade from organizations by
            # design (they should outlive/be independently auditable from
            # the org), so they need explicit cleanup — and flush()
            # between orgs matters, or a later org's set_tenant_context()
            # autoflushes this one's pending deletes under the WRONG
            # context and RLS silently drops them.
            await set_tenant_context(session, org.id)
            log_result = await session.execute(select(AuditLog).where(AuditLog.tenant_id == org.id))
            for log in log_result.scalars().all():
                await session.delete(log)
            membership_result = await session.execute(
                select(Membership).where(Membership.tenant_id == org.id)
            )
            for membership in membership_result.scalars().all():
                await session.delete(membership)
            await session.delete(org)
            await session.flush()

        user_result = await session.execute(select(User).where(User.email.like("endpoint-test-%")))
        for user in user_result.scalars().all():
            session_result = await session.execute(
                select(Session).where(Session.user_id == user.id)
            )
            for s in session_result.scalars().all():
                await session.delete(s)
            await session.delete(user)

        await session.commit()


async def _new_user_headers(email: str) -> dict[str, str]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Endpoint Test"
    )
    return auth_headers(token)


@pytest.mark.anyio
async def test_create_organization_requires_auth() -> None:
    response = client.post(
        "/organizations", json={"name": "No Auth", "slug": "endpoint-test-no-auth"}
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_create_organization() -> None:
    headers = await _new_user_headers("endpoint-test-create@example.com")
    response = client.post(
        "/organizations",
        json={"name": "Endpoint Test Org", "slug": "endpoint-test-create"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Endpoint Test Org"
    assert body["slug"] == "endpoint-test-create"
    assert "id" in body


@pytest.mark.anyio
async def test_creator_becomes_org_owner_and_can_read_it_back() -> None:
    headers = await _new_user_headers("endpoint-test-owner@example.com")
    create_response = client.post(
        "/organizations",
        json={"name": "Owner Test", "slug": "endpoint-test-owner-org"},
        headers=headers,
    )
    org_id = create_response.json()["id"]

    # Creator can immediately GET it back — proves the auto-created
    # org_owner membership + organization:read permission both work, not
    # just that creation itself succeeded.
    get_response = client.get(f"/organizations/{org_id}", headers=headers)
    assert get_response.status_code == 200


@pytest.mark.anyio
async def test_create_duplicate_slug_returns_409() -> None:
    headers = await _new_user_headers("endpoint-test-dup@example.com")
    client.post(
        "/organizations", json={"name": "First", "slug": "endpoint-test-dup"}, headers=headers
    )
    response = client.post(
        "/organizations", json={"name": "Second", "slug": "endpoint-test-dup"}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


@pytest.mark.anyio
async def test_create_with_invalid_slug_returns_422() -> None:
    headers = await _new_user_headers("endpoint-test-badslug@example.com")
    response = client.post(
        "/organizations",
        json={"name": "Bad Slug", "slug": "Not A Valid Slug!"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.anyio
async def test_get_nonexistent_organization_returns_403_not_404() -> None:
    # 403, not 404: get_current_tenant_id checks membership before the
    # route ever looks the org up, and a nonexistent org has no members
    # by definition — same response as "exists but you're not in it",
    # which is the point (doesn't confirm or deny existence either way).
    headers = await _new_user_headers("endpoint-test-getnone@example.com")
    response = client.get("/organizations/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 403


@pytest.mark.anyio
async def test_non_member_cannot_read_someone_elses_organization() -> None:
    owner_headers = await _new_user_headers("endpoint-test-org-owner-2@example.com")
    create_response = client.post(
        "/organizations",
        json={"name": "Private Org", "slug": "endpoint-test-private-org"},
        headers=owner_headers,
    )
    org_id = create_response.json()["id"]

    outsider_headers = await _new_user_headers("endpoint-test-outsider@example.com")
    response = client.get(f"/organizations/{org_id}", headers=outsider_headers)
    assert response.status_code == 403


@pytest.mark.anyio
async def test_get_and_delete_organization() -> None:
    headers = await _new_user_headers("endpoint-test-getdelete@example.com")
    create_response = client.post(
        "/organizations",
        json={"name": "Get Delete Test", "slug": "endpoint-test-get-delete"},
        headers=headers,
    )
    org_id = create_response.json()["id"]

    get_response = client.get(f"/organizations/{org_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["slug"] == "endpoint-test-get-delete"

    delete_response = client.delete(f"/organizations/{org_id}", headers=headers)
    assert delete_response.status_code == 204

    # Deleted, so no membership exists to check any more either —
    # correctly 403 rather than exploding.
    after_delete = client.get(f"/organizations/{org_id}", headers=headers)
    assert after_delete.status_code == 403

    # The org itself is gone, so the generic _cleanup fixture's
    # slug-based query won't find it to clean up its audit logs/
    # memberships (RLS requires a tenant context, and this is the only
    # place that still knows this specific org_id) — clean up here instead.
    async with get_session() as session:
        await set_tenant_context(session, uuid.UUID(org_id))
        log_result = await session.execute(
            select(AuditLog).where(AuditLog.tenant_id == uuid.UUID(org_id))
        )
        for log in log_result.scalars().all():
            await session.delete(log)
        membership_result = await session.execute(
            select(Membership).where(Membership.tenant_id == uuid.UUID(org_id))
        )
        for membership in membership_result.scalars().all():
            await session.delete(membership)
        await session.commit()


@pytest.mark.anyio
async def test_list_organizations_only_shows_callers_own_orgs() -> None:
    headers = await _new_user_headers("endpoint-test-list@example.com")
    for i in range(3):
        client.post(
            "/organizations",
            json={"name": f"List Test {i}", "slug": f"endpoint-test-list-{i}"},
            headers=headers,
        )

    other_headers = await _new_user_headers("endpoint-test-list-other@example.com")
    client.post(
        "/organizations",
        json={"name": "Someone Else's Org", "slug": "endpoint-test-list-other-org"},
        headers=other_headers,
    )

    response = client.get("/organizations", params={"limit": 2, "offset": 0}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) <= 2
    # 3 own orgs, not 4 — the other user's org must not appear.
    assert body["total"] == 3
