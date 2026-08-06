"""Proves repositories/base.py both works and actually filters by
tenant_id — not just relying on RLS to catch a missing filter."""

import pytest

from db import get_session, set_tenant_context
from models.organization import Organization
from repositories.workspace import WorkspaceRepository


@pytest.mark.anyio
async def test_create_get_list_delete_within_tenant() -> None:
    async with get_session() as session:
        org = Organization(name="Repo Test Org", slug="repo-test-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        repo = WorkspaceRepository(session, org.id)

        created = await repo.create(name="Engineering", slug="repo-eng")
        assert created.tenant_id == org.id

        fetched = await repo.get(created.id)
        assert fetched is not None
        assert fetched.slug == "repo-eng"

        listed = await repo.list()
        assert [w.slug for w in listed] == ["repo-eng"]

        await repo.delete(created)
        await session.flush()
        assert await repo.get(created.id) is None


@pytest.mark.anyio
async def test_create_ignores_caller_supplied_tenant_id() -> None:
    async with get_session() as session:
        org_a = Organization(name="Repo Org A", slug="repo-org-a")
        org_b = Organization(name="Repo Org B", slug="repo-org-b")
        session.add_all([org_a, org_b])
        await session.flush()
        await set_tenant_context(session, org_a.id)

        repo = WorkspaceRepository(session, org_a.id)

        # Even if a caller passes tenant_id explicitly, the repository's
        # own tenant_id wins — a caller can't spoof a different tenant
        # through this layer.
        created = await repo.create(name="Spoof Attempt", slug="repo-spoof", tenant_id=org_b.id)
        assert created.tenant_id == org_a.id


@pytest.mark.anyio
async def test_list_only_returns_current_tenants_rows() -> None:
    async with get_session() as session:
        org_a = Organization(name="Repo List Org A", slug="repo-list-org-a")
        org_b = Organization(name="Repo List Org B", slug="repo-list-org-b")
        session.add_all([org_a, org_b])
        await session.flush()

        await set_tenant_context(session, org_a.id)
        await WorkspaceRepository(session, org_a.id).create(name="A WS", slug="repo-list-a-ws")

        await set_tenant_context(session, org_b.id)
        await WorkspaceRepository(session, org_b.id).create(name="B WS", slug="repo-list-b-ws")

        repo_a = WorkspaceRepository(session, org_a.id)
        await set_tenant_context(session, org_a.id)
        results = await repo_a.list()
        assert [w.slug for w in results] == ["repo-list-a-ws"]
