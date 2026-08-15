"""RBAC-enforcement tests (roadmap step 081, closing Milestone 2).

Role-based blocking is already spot-checked per-feature elsewhere (e.g.
test_workspace_endpoints.py's test_end_user_role_cannot_create_workspace,
test_invitation_endpoints.py's test_end_user_role_cannot_create_invitation,
test_security_settings_endpoints.py's test_end_user_cannot_read_or_update_
security_settings) -- all against the same one role, end_user, which has
almost no permissions at all. What's missing, and what this file adds:

1. A systematic check that the ACTUAL seeded role->permission matrix
   (migrations 1d0ef14faf9e, 017f224e6497, 3a7618936d79, 7f502a484e54)
   matches the intended design, not just that some one permission for
   some one role happens to work -- a new permission granted to the
   wrong roles (or forgotten for the right ones) would pass every
   existing per-feature test and still be wrong.
2. Real HTTP-level tests for tier distinctions nothing else covers:
   admin has organization:update but not organization:delete (the
   org_owner-only carve-out, not just "member vs non-member"); manager
   has broad workspace/invitation access but not security_settings (the
   security-tier carve-out, step 079); viewer can read a workspace but
   not delete one (a read-only role that isn't end_user).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.invitation import Invitation
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.security_settings import SecuritySettings
from models.session import Session
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)

# The intended design (AGENTS.md role matrix), as actually seeded across
# every permission-catalog migration to date. guest is deliberately
# absent from both sides -- zero permissions, so zero rows either way.
EXPECTED_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "org_owner": {
        "organization:read",
        "organization:update",
        "organization:delete",
        "workspace:create",
        "workspace:read",
        "workspace:delete",
        "invitation:create",
        "invitation:read",
        "invitation:revoke",
        "security_settings:read",
        "security_settings:update",
        "knowledge_base:create",
        "knowledge_base:read",
        "knowledge_base:delete",
        "assistant:create",
        "assistant:read",
        "assistant:delete",
        "document:create",
        "document:read",
        "document:update",
        "document:delete",
        "conversation:create",
        "conversation:read",
        "message:create",
    },
    "admin": {
        "organization:read",
        "organization:update",
        "workspace:create",
        "workspace:read",
        "workspace:delete",
        "invitation:create",
        "invitation:read",
        "invitation:revoke",
        "security_settings:read",
        "security_settings:update",
        "knowledge_base:create",
        "knowledge_base:read",
        "knowledge_base:delete",
        "assistant:create",
        "assistant:read",
        "assistant:delete",
        "document:create",
        "document:read",
        "document:update",
        "document:delete",
        "conversation:create",
        "conversation:read",
        "message:create",
    },
    "manager": {
        "organization:read",
        "workspace:create",
        "workspace:read",
        "workspace:delete",
        "invitation:create",
        "invitation:read",
        "invitation:revoke",
        "knowledge_base:create",
        "knowledge_base:read",
        "knowledge_base:delete",
        "assistant:create",
        "assistant:read",
        "assistant:delete",
        "document:create",
        "document:read",
        "document:update",
        "document:delete",
        "conversation:create",
        "conversation:read",
        "message:create",
    },
    "knowledge_manager": {
        "organization:read",
        "workspace:read",
        "conversation:create",
        "conversation:read",
        "message:create",
    },
    "developer": {
        "organization:read",
        "workspace:read",
        "conversation:create",
        "conversation:read",
        "message:create",
    },
    "support_agent": {
        "organization:read",
        "workspace:read",
        "conversation:create",
        "conversation:read",
        "message:create",
    },
    "analyst": {
        "organization:read",
        "workspace:read",
        "conversation:create",
        "conversation:read",
        "message:create",
    },
    "viewer": {"organization:read", "workspace:read", "conversation:read"},
    "end_user": {"workspace:read", "conversation:create", "conversation:read", "message:create"},
    "guest": set(),
}


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Invitation, SecuritySettings, Workspace, AuditLog, Membership):
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
        client, email=email, password="correct horse battery staple", full_name="RBAC Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "RBAC Test Org", "slug": f"endpoint-test-rbac-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


async def _add_member_with_role(org_id: uuid.UUID, email: str, role_name: str) -> dict[str, str]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name=role_name
    )
    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        role_result = await session.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one()
        await set_tenant_context(session, org_id)
        session.add(
            Membership(tenant_id=org_id, user_id=user.id, workspace_id=None, role_id=role.id)
        )
        await session.commit()
    return auth_headers(token)


@pytest.mark.anyio
async def test_seeded_role_permission_matrix_matches_intended_design() -> None:
    async with get_session() as session:
        result = await session.execute(
            text("""
                SELECT r.name AS role, p.key AS permission
                FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
            """)
        )
        actual: dict[str, set[str]] = {}
        for row in result.all():
            actual.setdefault(row.role, set()).add(row.permission)

    for role_name, expected_permissions in EXPECTED_ROLE_PERMISSIONS.items():
        assert actual.get(role_name, set()) == expected_permissions, (
            f"role '{role_name}': expected {expected_permissions}, "
            f"got {actual.get(role_name, set())}"
        )


@pytest.mark.anyio
async def test_admin_can_read_but_not_delete_organization() -> None:
    """organization:update exists in the permission catalog but has no
    route enforcing it yet (routers/organization.py has no update
    endpoint at all) -- not tested here, since there'd be nothing real
    to assert against. organization:delete does have one, and IS the
    org_owner-only carve-out this test targets."""
    owner_email = "endpoint-test-rbac-admin-owner@example.com"
    org_id, owner_headers = _new_org(owner_email)
    try:
        admin_headers = await _add_member_with_role(
            org_id, "endpoint-test-rbac-admin@example.com", "admin"
        )

        read_response = client.get(f"/organizations/{org_id}", headers=admin_headers)
        assert read_response.status_code == 200

        delete_response = client.delete(f"/organizations/{org_id}", headers=admin_headers)
        assert delete_response.status_code == 403

        owner_delete = client.delete(f"/organizations/{org_id}", headers=owner_headers)
        assert owner_delete.status_code == 204
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-rbac-admin@example.com")


@pytest.mark.anyio
async def test_manager_has_broad_access_but_not_security_settings() -> None:
    owner_email = "endpoint-test-rbac-manager-owner@example.com"
    org_id, _owner_headers = _new_org(owner_email)
    try:
        manager_headers = await _add_member_with_role(
            org_id, "endpoint-test-rbac-manager@example.com", "manager"
        )

        create_workspace = client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Manager WS", "slug": "endpoint-test-rbac-manager-ws"},
            headers=manager_headers,
        )
        assert create_workspace.status_code == 201

        create_invitation = client.post(
            f"/organizations/{org_id}/invitations",
            json={"email": "someone@example.com", "role_name": "viewer"},
            headers=manager_headers,
        )
        assert create_invitation.status_code == 201

        security_get = client.get(
            f"/organizations/{org_id}/security-settings", headers=manager_headers
        )
        assert security_get.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-rbac-manager@example.com")


@pytest.mark.anyio
async def test_viewer_can_read_workspace_but_not_delete_it() -> None:
    owner_email = "endpoint-test-rbac-viewer-owner@example.com"
    org_id, owner_headers = _new_org(owner_email)
    try:
        create_response = client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "Viewer WS", "slug": "endpoint-test-rbac-viewer-ws"},
            headers=owner_headers,
        )
        workspace_id = create_response.json()["id"]

        viewer_headers = await _add_member_with_role(
            org_id, "endpoint-test-rbac-viewer@example.com", "viewer"
        )

        read_response = client.get(
            f"/organizations/{org_id}/workspaces/{workspace_id}", headers=viewer_headers
        )
        assert read_response.status_code == 200

        delete_response = client.delete(
            f"/organizations/{org_id}/workspaces/{workspace_id}", headers=viewer_headers
        )
        assert delete_response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-rbac-viewer@example.com")


@pytest.mark.anyio
async def test_guest_role_has_no_permissions_at_all() -> None:
    owner_email = "endpoint-test-rbac-guest-owner@example.com"
    org_id, _owner_headers = _new_org(owner_email)
    try:
        guest_headers = await _add_member_with_role(
            org_id, "endpoint-test-rbac-guest@example.com", "guest"
        )

        # Even organization:read -- every other role in the matrix has at
        # least this much.
        response = client.get(f"/organizations/{org_id}", headers=guest_headers)
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-rbac-guest@example.com")
