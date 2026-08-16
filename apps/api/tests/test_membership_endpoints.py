"""Integration tests against the real FastAPI app for
routers/membership.py (roadmap step 239, user/role-management UI's
own real backend gap -- no membership listing/role-update/removal
endpoint existed anywhere before this step).
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
from models.role import Role
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


def _new_org(email: str) -> tuple[uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Membership Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Membership Test Org", "slug": f"endpoint-test-membership-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


async def _add_member_with_role(
    org_id: uuid.UUID, email: str, role_name: str
) -> tuple[uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name=role_name
    )
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        role_result = await session.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one()
        await set_tenant_context(session, org_id)
        membership = Membership(
            tenant_id=org_id, user_id=user.id, workspace_id=None, role_id=role.id
        )
        session.add(membership)
        await session.commit()
        membership_id = membership.id
    return membership_id, auth_headers(token)


@pytest.mark.anyio
async def test_owner_can_list_members_with_role_names() -> None:
    owner_email = "endpoint-test-membership-list-owner@example.com"
    org_id, owner_headers = _new_org(owner_email)
    member_email = "endpoint-test-membership-list-member@example.com"
    try:
        await _add_member_with_role(org_id, member_email, "manager")

        response = client.get(f"/organizations/{org_id}/members", headers=owner_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        emails_to_roles = {item["email"]: item["role_name"] for item in body["items"]}
        assert emails_to_roles[owner_email] == "org_owner"
        assert emails_to_roles[member_email] == "manager"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(member_email)


@pytest.mark.anyio
async def test_owner_can_change_a_members_role() -> None:
    owner_email = "endpoint-test-membership-change-owner@example.com"
    org_id, owner_headers = _new_org(owner_email)
    member_email = "endpoint-test-membership-change-member@example.com"
    try:
        membership_id, _member_headers = await _add_member_with_role(
            org_id, member_email, "manager"
        )

        response = client.patch(
            f"/organizations/{org_id}/members/{membership_id}",
            json={"role_name": "viewer"},
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert response.json()["role_name"] == "viewer"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(member_email)


@pytest.mark.anyio
async def test_non_owner_cannot_promote_someone_to_org_owner() -> None:
    owner_email = "endpoint-test-membership-promote-owner@example.com"
    org_id, _owner_headers = _new_org(owner_email)
    admin_email = "endpoint-test-membership-promote-admin@example.com"
    member_email = "endpoint-test-membership-promote-member@example.com"
    try:
        _admin_id, admin_headers = await _add_member_with_role(org_id, admin_email, "admin")
        membership_id, _member_headers = await _add_member_with_role(
            org_id, member_email, "manager"
        )

        response = client.patch(
            f"/organizations/{org_id}/members/{membership_id}",
            json={"role_name": "org_owner"},
            headers=admin_headers,
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(admin_email)
        await _cleanup_user(member_email)


@pytest.mark.anyio
async def test_cannot_demote_the_last_owner_but_can_once_a_second_owner_exists() -> None:
    owner_email = "endpoint-test-membership-lastowner-owner@example.com"
    org_id, owner_headers = _new_org(owner_email)
    member_email = "endpoint-test-membership-lastowner-member@example.com"
    try:
        membership_id, member_headers = await _add_member_with_role(org_id, member_email, "manager")

        # Promote the second member to org_owner too -- now there are 2.
        promote_response = client.patch(
            f"/organizations/{org_id}/members/{membership_id}",
            json={"role_name": "org_owner"},
            headers=owner_headers,
        )
        assert promote_response.status_code == 200

        # Find the ORIGINAL owner's own membership_id via the list endpoint.
        list_response = client.get(f"/organizations/{org_id}/members", headers=owner_headers)
        original_owner_membership_id = next(
            item["id"] for item in list_response.json()["items"] if item["email"] == owner_email
        )

        # With 2 owners, demoting one now succeeds.
        demote_response = client.patch(
            f"/organizations/{org_id}/members/{original_owner_membership_id}",
            json={"role_name": "viewer"},
            headers=member_headers,
        )
        assert demote_response.status_code == 200

        # Now only 1 owner remains (the former member) -- demoting THAT
        # one must be blocked.
        last_owner_response = client.patch(
            f"/organizations/{org_id}/members/{membership_id}",
            json={"role_name": "viewer"},
            headers=member_headers,
        )
        assert last_owner_response.status_code == 409
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(member_email)


@pytest.mark.anyio
async def test_cannot_change_or_remove_your_own_membership() -> None:
    owner_email = "endpoint-test-membership-self-owner@example.com"
    org_id, owner_headers = _new_org(owner_email)
    try:
        list_response = client.get(f"/organizations/{org_id}/members", headers=owner_headers)
        own_membership_id = list_response.json()["items"][0]["id"]

        patch_response = client.patch(
            f"/organizations/{org_id}/members/{own_membership_id}",
            json={"role_name": "admin"},
            headers=owner_headers,
        )
        assert patch_response.status_code == 409

        delete_response = client.delete(
            f"/organizations/{org_id}/members/{own_membership_id}", headers=owner_headers
        )
        assert delete_response.status_code == 409
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)


@pytest.mark.anyio
async def test_admin_can_remove_a_regular_member() -> None:
    owner_email = "endpoint-test-membership-remove-owner@example.com"
    org_id, _owner_headers = _new_org(owner_email)
    admin_email = "endpoint-test-membership-remove-admin@example.com"
    member_email = "endpoint-test-membership-remove-member@example.com"
    try:
        _admin_id, admin_headers = await _add_member_with_role(org_id, admin_email, "admin")
        membership_id, _member_headers = await _add_member_with_role(
            org_id, member_email, "manager"
        )

        response = client.delete(
            f"/organizations/{org_id}/members/{membership_id}", headers=admin_headers
        )
        assert response.status_code == 204

        list_response = client.get(f"/organizations/{org_id}/members", headers=admin_headers)
        assert member_email not in {item["email"] for item in list_response.json()["items"]}
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(admin_email)
        await _cleanup_user(member_email)


@pytest.mark.anyio
async def test_updating_to_a_nonexistent_role_returns_404() -> None:
    owner_email = "endpoint-test-membership-badrole-owner@example.com"
    org_id, owner_headers = _new_org(owner_email)
    member_email = "endpoint-test-membership-badrole-member@example.com"
    try:
        membership_id, _member_headers = await _add_member_with_role(
            org_id, member_email, "manager"
        )

        response = client.patch(
            f"/organizations/{org_id}/members/{membership_id}",
            json={"role_name": "not_a_real_role"},
            headers=owner_headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(member_email)


@pytest.mark.anyio
async def test_end_user_role_cannot_list_update_or_delete_members() -> None:
    owner_email = "endpoint-test-membership-enduser-owner@example.com"
    org_id, owner_headers = _new_org(owner_email)
    end_user_email = "endpoint-test-membership-enduser-member@example.com"
    other_email = "endpoint-test-membership-enduser-other@example.com"
    try:
        _end_user_id, end_user_headers = await _add_member_with_role(
            org_id, end_user_email, "end_user"
        )
        other_membership_id, _other_headers = await _add_member_with_role(
            org_id, other_email, "viewer"
        )

        list_response = client.get(f"/organizations/{org_id}/members", headers=end_user_headers)
        assert list_response.status_code == 403

        patch_response = client.patch(
            f"/organizations/{org_id}/members/{other_membership_id}",
            json={"role_name": "manager"},
            headers=end_user_headers,
        )
        assert patch_response.status_code == 403

        delete_response = client.delete(
            f"/organizations/{org_id}/members/{other_membership_id}", headers=end_user_headers
        )
        assert delete_response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(end_user_email)
        await _cleanup_user(other_email)
