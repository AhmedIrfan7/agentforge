"""Integration tests against the real FastAPI app for
routers/security_settings.py (roadmap step 079) — including the
mfa_required enforcement wired into dependencies/tenant.py.
"""

import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.security_settings import SecuritySettings
from models.session import Session
from models.user import User
from models.workspace import Workspace
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (SecuritySettings, Workspace, AuditLog, Membership):
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
        client, email=email, password="correct horse battery staple", full_name="Security Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Security Test Org", "slug": f"endpoint-test-sec-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


def test_get_security_settings_requires_auth() -> None:
    response = client.get(f"/organizations/{uuid.uuid4()}/security-settings")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_get_returns_defaults_for_new_org() -> None:
    email = "endpoint-test-sec-owner-1@example.com"
    org_id, headers = _new_org(email)
    try:
        response = client.get(f"/organizations/{org_id}/security-settings", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == str(org_id)
        assert body["mfa_required"] is False
        assert body["session_timeout_minutes"] is None
        assert body["password_min_length"] is None
        assert body["password_require_uppercase"] is False
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_patch_only_changes_included_fields() -> None:
    email = "endpoint-test-sec-owner-2@example.com"
    org_id, headers = _new_org(email)
    try:
        first = client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"password_min_length": 12},
            headers=headers,
        )
        assert first.status_code == 200
        assert first.json()["password_min_length"] == 12
        assert first.json()["password_require_uppercase"] is False

        second = client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"password_require_uppercase": True},
            headers=headers,
        )
        assert second.status_code == 200
        # Untouched by the second PATCH — proves partial update semantics.
        assert second.json()["password_min_length"] == 12
        assert second.json()["password_require_uppercase"] is True
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_patch_can_explicitly_clear_a_field_to_null() -> None:
    email = "endpoint-test-sec-owner-3@example.com"
    org_id, headers = _new_org(email)
    try:
        client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"session_timeout_minutes": 30},
            headers=headers,
        )
        response = client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"session_timeout_minutes": None},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["session_timeout_minutes"] is None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_cannot_read_or_update_security_settings() -> None:
    owner_email = "endpoint-test-sec-owner-4@example.com"
    org_id, _owner_headers = _new_org(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-sec-member@example.com",
            password="correct horse battery staple",
            full_name="End User",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-sec-member@example.com")
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

        member_headers = auth_headers(member_token)
        get_response = client.get(
            f"/organizations/{org_id}/security-settings", headers=member_headers
        )
        assert get_response.status_code == 403

        patch_response = client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"mfa_required": True},
            headers=member_headers,
        )
        assert patch_response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-sec-member@example.com")


@pytest.mark.anyio
async def test_mfa_required_blocks_members_without_mfa_enabled() -> None:
    owner_email = "endpoint-test-sec-mfareq-owner@example.com"
    org_id, headers = _new_org(owner_email)
    try:
        # Owner hasn't enabled MFA on their own account yet.
        get_before = client.get(f"/organizations/{org_id}", headers=headers)
        assert get_before.status_code == 200

        patch_response = client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"mfa_required": True},
            headers=headers,
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["mfa_required"] is True

        # Same owner, same membership, no MFA on the account -- now blocked
        # from every tenant-scoped route, not just security-settings.
        get_after = client.get(f"/organizations/{org_id}", headers=headers)
        assert get_after.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)


@pytest.mark.anyio
async def test_mfa_required_allows_access_once_mfa_is_enabled() -> None:
    owner_email = "endpoint-test-sec-mfaok-owner@example.com"
    org_id, headers = _new_org(owner_email)
    try:
        client.patch(
            f"/organizations/{org_id}/security-settings",
            json={"mfa_required": True},
            headers=headers,
        )
        assert client.get(f"/organizations/{org_id}", headers=headers).status_code == 403

        enroll = client.post("/auth/mfa/enroll", headers=headers)
        secret = enroll.json()["secret"]
        code = pyotp.TOTP(secret).now()
        confirm = client.post("/auth/mfa/confirm", json={"code": code}, headers=headers)
        assert confirm.status_code == 200

        response = client.get(f"/organizations/{org_id}", headers=headers)
        assert response.status_code == 200
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
