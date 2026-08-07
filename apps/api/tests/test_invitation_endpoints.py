"""Integration tests against the real FastAPI app for routers/invitation.py
(roadmap step 073 — create only; accept is step 074, not implemented yet).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.invitation import Invitation
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.session import Session
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Invitation, Workspace, AuditLog, Membership):
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


async def _new_org(email: str) -> tuple[uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Invitation Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Invitation Test Org", "slug": f"endpoint-test-inv-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


def test_create_invitation_requires_auth() -> None:
    response = client.post(
        f"/organizations/{uuid.uuid4()}/invitations",
        json={"email": "someone@example.com", "role_name": "viewer"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_create_invitation_as_org_owner() -> None:
    email = "endpoint-test-inv-owner-1@example.com"
    org_id, headers = await _new_org(email)
    try:
        response = client.post(
            f"/organizations/{org_id}/invitations",
            json={"email": "invitee@example.com", "role_name": "viewer"},
            headers=headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "invitee@example.com"
        assert body["tenant_id"] == str(org_id)
        assert body["accepted_at"] is None
        assert body["revoked_at"] is None
        # The raw token must never appear in the API response — it only
        # ever leaves the system via the emailed link.
        assert "token" not in body
        assert "token_hash" not in body
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_create_duplicate_pending_invitation_returns_409() -> None:
    email = "endpoint-test-inv-owner-2@example.com"
    org_id, headers = await _new_org(email)
    try:
        client.post(
            f"/organizations/{org_id}/invitations",
            json={"email": "invitee-dup@example.com", "role_name": "viewer"},
            headers=headers,
        )
        response = client.post(
            f"/organizations/{org_id}/invitations",
            json={"email": "invitee-dup@example.com", "role_name": "viewer"},
            headers=headers,
        )
        assert response.status_code == 409
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_create_invitation_with_unknown_role_returns_404() -> None:
    email = "endpoint-test-inv-owner-3@example.com"
    org_id, headers = await _new_org(email)
    try:
        response = client.post(
            f"/organizations/{org_id}/invitations",
            json={"email": "invitee@example.com", "role_name": "not_a_real_role"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_create_invitation_with_foreign_workspace_returns_404() -> None:
    email = "endpoint-test-inv-owner-4@example.com"
    org_id, headers = await _new_org(email)
    try:
        response = client.post(
            f"/organizations/{org_id}/invitations",
            json={
                "email": "invitee@example.com",
                "role_name": "viewer",
                "workspace_id": str(uuid.uuid4()),
            },
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_create_invitation() -> None:
    """end_user has no invitation:create grant (migration 017f224e6497) —
    proves the permission check actually runs, not just membership."""
    owner_email = "endpoint-test-inv-owner-5@example.com"
    org_id, _owner_headers = await _new_org(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-inv-member@example.com",
            password="correct horse battery staple",
            full_name="End User Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-inv-member@example.com")
            )
            member_user = result.scalar_one()

            role_result = await session.execute(select(Role).where(Role.name == "end_user"))
            end_user_role = role_result.scalar_one()

            await set_tenant_context(session, org_id)
            session.add(
                Membership(
                    tenant_id=org_id,
                    user_id=member_user.id,
                    workspace_id=None,
                    role_id=end_user_role.id,
                )
            )
            await session.commit()

        response = client.post(
            f"/organizations/{org_id}/invitations",
            json={"email": "invitee@example.com", "role_name": "viewer"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-inv-member@example.com")


@pytest.mark.anyio
async def test_invitation_create_is_audited() -> None:
    email = "endpoint-test-inv-owner-6@example.com"
    org_id, headers = await _new_org(email)
    try:
        create_response = client.post(
            f"/organizations/{org_id}/invitations",
            json={"email": "invitee@example.com", "role_name": "viewer"},
            headers=headers,
        )
        invitation_id = uuid.UUID(create_response.json()["id"])

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(AuditLog).where(AuditLog.resource_id == invitation_id)
            )
            logs = result.scalars().all()
            assert [log.action for log in logs] == ["invitation.create"]
            assert logs[0].tenant_id == org_id
            assert logs[0].actor_user_id is not None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
