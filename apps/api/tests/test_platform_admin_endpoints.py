"""Integration tests against the real FastAPI app for
routers/platform_admin.py (roadmap step 249) -- the first real
cross-org view, proving the per-org RLS-respecting loop (set_tenant_
context called once per organization, never bypassed) actually returns
correct, isolated counts for each tenant.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.conversation import Conversation
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.membership import Membership
from models.organization import Organization
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _make_platform_admin(email: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.is_platform_admin = True
        await session.commit()


def _new_org(email: str, name: str) -> tuple[uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client,
        email=email,
        password="correct horse battery staple",
        full_name="Platform Admin Test",
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": name, "slug": f"endpoint-test-platform-admin-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


async def _new_workspace_and_conversation(org_id: uuid.UUID, headers: dict[str, str]) -> None:
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Platform Admin WS", "slug": "endpoint-test-platform-admin-ws"},
        headers=headers,
    )
    workspace_id = ws_response.json()["id"]
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Platform Admin KB", "slug": "endpoint-test-platform-admin-kb"},
        headers=headers,
    )
    kb_id = kb_response.json()["id"]
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Platform Admin Bot", "slug": "endpoint-test-platform-admin-bot"},
        headers=headers,
    )
    assistant_id = asst_response.json()["id"]

    async with get_session() as session:
        await set_tenant_context(session, org_id)
        session.add(Conversation(tenant_id=org_id, assistant_id=uuid.UUID(assistant_id)))
        session.add(
            Document(
                tenant_id=org_id,
                knowledge_base_id=uuid.UUID(kb_id),
                title="Doc",
                status="embedded",
                storage_key="endpoint-test-platform-admin/doc.txt",
                content_type="text/plain",
                size_bytes=10,
            )
        )
        await session.commit()


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Document, Conversation, KnowledgeBase, Workspace, Membership):
            result = await session.execute(select(model).where(model.tenant_id == org_id))
            for row in result.scalars().all():
                await session.delete(row)
            await session.flush()
        org = await session.get(Organization, org_id)
        if org is not None:
            await session.delete(org)
        await session.commit()


async def _cleanup_user(email: str) -> None:
    from models.session import Session

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
async def test_platform_admin_sees_real_counts_isolated_per_organization() -> None:
    admin_email = "endpoint-test-platform-admin-owner@example.com"
    other_email = "endpoint-test-platform-admin-other@example.com"
    admin_org_id, admin_headers = _new_org(admin_email, "Platform Admin Org A")
    other_org_id, other_headers = _new_org(other_email, "Platform Admin Org B")
    try:
        await _make_platform_admin(admin_email)
        await _new_workspace_and_conversation(admin_org_id, admin_headers)
        # A second org with its own real data -- proves isolation, not
        # just that a single org's counts render correctly.
        client.post(
            f"/organizations/{other_org_id}/workspaces",
            json={"name": "Other WS", "slug": "endpoint-test-platform-admin-other-ws"},
            headers=other_headers,
        )

        response = client.get("/platform-admin/organizations", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        by_id = {org["id"]: org for org in body["organizations"]}

        admin_org = by_id[str(admin_org_id)]
        assert admin_org["workspace_count"] == 1
        assert admin_org["member_count"] == 1
        assert admin_org["conversation_count"] == 1
        assert admin_org["document_count"] == 1

        other_org = by_id[str(other_org_id)]
        assert other_org["workspace_count"] == 1
        assert other_org["conversation_count"] == 0
        assert other_org["document_count"] == 0
    finally:
        await _cleanup_org(admin_org_id)
        await _cleanup_org(other_org_id)
        await _cleanup_user(admin_email)
        await _cleanup_user(other_email)


@pytest.mark.anyio
async def test_non_platform_admin_cannot_read_cross_org_view() -> None:
    email = "endpoint-test-platform-admin-regular@example.com"
    org_id, headers = _new_org(email, "Platform Admin Org C")
    try:
        response = client.get("/platform-admin/organizations", headers=headers)
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_unauthenticated_request_is_rejected() -> None:
    response = client.get("/platform-admin/organizations")
    assert response.status_code == 401
