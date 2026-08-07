"""Integration tests against the real FastAPI app for routers/invitation.py
(roadmap steps 073 create, 074 accept, 075 list/revoke + status).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth.verification import generate_invitation_token
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
from repositories.invitation import InvitationRepository
from repositories.role import RoleRepository
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


async def _new_invitation(
    org_id: uuid.UUID,
    email: str,
    *,
    role_name: str = "viewer",
    expired: bool = False,
) -> tuple[str, uuid.UUID]:
    """Seeds an Invitation row directly (bypassing the create endpoint and
    its stub email) with a known raw token — same reasoning as
    tests/test_verify_email_endpoint.py using generate_verification_token()
    directly rather than scraping the logged email body."""
    raw_token, token_hash, expires_at = generate_invitation_token()
    if expired:
        expires_at = datetime.now(UTC) - timedelta(hours=1)
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        role = await RoleRepository(session).get_by_name(role_name)
        assert role is not None
        owner_result = await session.execute(
            select(Membership).where(Membership.tenant_id == org_id).limit(1)
        )
        owner_membership = owner_result.scalar_one()
        invitation = await InvitationRepository(session, org_id).create(
            email=email,
            role_id=role.id,
            workspace_id=None,
            invited_by_user_id=owner_membership.user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await session.commit()
        return raw_token, invitation.id


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


def test_accept_invitation_requires_auth() -> None:
    response = client.post("/invitations/accept", json={"token": "not-a-real-token"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_accept_invitation_creates_membership() -> None:
    owner_email = "endpoint-test-inv-accept-owner-1@example.com"
    invitee_email = "endpoint-test-inv-accept-invitee-1@example.com"
    org_id, _owner_headers = await _new_org(owner_email)
    try:
        raw_token, invitation_id = await _new_invitation(org_id, invitee_email, role_name="viewer")
        invitee_token = signup_and_login(
            client,
            email=invitee_email,
            password="correct horse battery staple",
            full_name="Invitee",
        )

        response = client.post(
            "/invitations/accept",
            json={"token": raw_token},
            headers=auth_headers(invitee_token),
        )
        assert response.status_code == 204

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            invitation = await session.get(Invitation, invitation_id)
            assert invitation is not None
            assert invitation.accepted_at is not None

            user_result = await session.execute(select(User).where(User.email == invitee_email))
            invitee = user_result.scalar_one()
            membership_result = await session.execute(
                select(Membership).where(
                    Membership.tenant_id == org_id, Membership.user_id == invitee.id
                )
            )
            membership = membership_result.scalar_one()
            assert membership.role_id == invitation.role_id
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(invitee_email)


@pytest.mark.anyio
async def test_accept_invitation_with_wrong_account_returns_403() -> None:
    owner_email = "endpoint-test-inv-accept-owner-2@example.com"
    wrong_email = "endpoint-test-inv-accept-wrong-2@example.com"
    org_id, _owner_headers = await _new_org(owner_email)
    try:
        raw_token, _invitation_id = await _new_invitation(
            org_id, "someone-else-2@example.com", role_name="viewer"
        )
        wrong_token = signup_and_login(
            client, email=wrong_email, password="correct horse battery staple", full_name="Wrong"
        )

        response = client.post(
            "/invitations/accept",
            json={"token": raw_token},
            headers=auth_headers(wrong_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(wrong_email)


@pytest.mark.anyio
async def test_accept_expired_invitation_returns_401() -> None:
    owner_email = "endpoint-test-inv-accept-owner-3@example.com"
    invitee_email = "endpoint-test-inv-accept-invitee-3@example.com"
    org_id, _owner_headers = await _new_org(owner_email)
    try:
        raw_token, _invitation_id = await _new_invitation(
            org_id, invitee_email, role_name="viewer", expired=True
        )
        invitee_token = signup_and_login(
            client,
            email=invitee_email,
            password="correct horse battery staple",
            full_name="Invitee",
        )

        response = client.post(
            "/invitations/accept",
            json={"token": raw_token},
            headers=auth_headers(invitee_token),
        )
        assert response.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(invitee_email)


@pytest.mark.anyio
async def test_accept_unknown_token_returns_401() -> None:
    invitee_email = "endpoint-test-inv-accept-invitee-4@example.com"
    invitee_token = signup_and_login(
        client,
        email=invitee_email,
        password="correct horse battery staple",
        full_name="Invitee",
    )
    try:
        response = client.post(
            "/invitations/accept",
            json={"token": "totally-bogus-token"},
            headers=auth_headers(invitee_token),
        )
        assert response.status_code == 401
    finally:
        await _cleanup_user(invitee_email)


@pytest.mark.anyio
async def test_accept_already_accepted_invitation_returns_401() -> None:
    owner_email = "endpoint-test-inv-accept-owner-5@example.com"
    invitee_email = "endpoint-test-inv-accept-invitee-5@example.com"
    org_id, _owner_headers = await _new_org(owner_email)
    try:
        raw_token, _invitation_id = await _new_invitation(org_id, invitee_email, role_name="viewer")
        invitee_token = signup_and_login(
            client,
            email=invitee_email,
            password="correct horse battery staple",
            full_name="Invitee",
        )
        headers = auth_headers(invitee_token)

        first = client.post("/invitations/accept", json={"token": raw_token}, headers=headers)
        assert first.status_code == 204

        second = client.post("/invitations/accept", json={"token": raw_token}, headers=headers)
        assert second.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(invitee_email)


@pytest.mark.anyio
async def test_accept_invitation_is_audited() -> None:
    owner_email = "endpoint-test-inv-accept-owner-6@example.com"
    invitee_email = "endpoint-test-inv-accept-invitee-6@example.com"
    org_id, _owner_headers = await _new_org(owner_email)
    try:
        raw_token, invitation_id = await _new_invitation(org_id, invitee_email, role_name="viewer")
        invitee_token = signup_and_login(
            client,
            email=invitee_email,
            password="correct horse battery staple",
            full_name="Invitee",
        )

        client.post(
            "/invitations/accept", json={"token": raw_token}, headers=auth_headers(invitee_token)
        )

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(AuditLog)
                .where(AuditLog.resource_id == invitation_id)
                .order_by(AuditLog.created_at)
            )
            logs = result.scalars().all()
            # _new_invitation seeds the row directly via the repository, not
            # the audited create endpoint, so accept is the only log here.
            assert [log.action for log in logs] == ["invitation.accept"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(invitee_email)


def test_list_invitations_requires_auth() -> None:
    response = client.get(f"/organizations/{uuid.uuid4()}/invitations")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_list_invitations_shows_derived_status() -> None:
    owner_email = "endpoint-test-inv-list-owner-1@example.com"
    org_id, headers = await _new_org(owner_email)
    try:
        _pending_token, pending_id = await _new_invitation(
            org_id, "pending@example.com", role_name="viewer"
        )
        _expired_token, expired_id = await _new_invitation(
            org_id, "expired@example.com", role_name="viewer", expired=True
        )
        accepted_token, accepted_id = await _new_invitation(
            org_id, "accepted@example.com", role_name="viewer"
        )
        revoked_token, revoked_id = await _new_invitation(
            org_id, "revoked@example.com", role_name="viewer"
        )

        accepted_email = "accepted@example.com"
        accepted_user_token = signup_and_login(
            client,
            email=accepted_email,
            password="correct horse battery staple",
            full_name="Accepted",
        )
        client.post(
            "/invitations/accept",
            json={"token": accepted_token},
            headers=auth_headers(accepted_user_token),
        )
        client.delete(
            f"/organizations/{org_id}/invitations/{revoked_id}",
            headers=headers,
        )

        response = client.get(
            f"/organizations/{org_id}/invitations", params={"limit": 50}, headers=headers
        )
        assert response.status_code == 200
        by_id = {item["id"]: item["status"] for item in response.json()["items"]}
        assert by_id[str(pending_id)] == "pending"
        assert by_id[str(expired_id)] == "expired"
        assert by_id[str(accepted_id)] == "accepted"
        assert by_id[str(revoked_id)] == "revoked"
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(accepted_email)


@pytest.mark.anyio
async def test_end_user_cannot_list_invitations() -> None:
    owner_email = "endpoint-test-inv-list-owner-2@example.com"
    org_id, _owner_headers = await _new_org(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-inv-list-member@example.com",
            password="correct horse battery staple",
            full_name="End User Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-inv-list-member@example.com")
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

        response = client.get(
            f"/organizations/{org_id}/invitations", headers=auth_headers(member_token)
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-inv-list-member@example.com")


@pytest.mark.anyio
async def test_revoke_invitation_blocks_later_accept() -> None:
    owner_email = "endpoint-test-inv-revoke-owner-1@example.com"
    invitee_email = "endpoint-test-inv-revoke-invitee-1@example.com"
    org_id, headers = await _new_org(owner_email)
    try:
        raw_token, invitation_id = await _new_invitation(org_id, invitee_email, role_name="viewer")

        revoke_response = client.delete(
            f"/organizations/{org_id}/invitations/{invitation_id}", headers=headers
        )
        assert revoke_response.status_code == 204

        invitee_token = signup_and_login(
            client,
            email=invitee_email,
            password="correct horse battery staple",
            full_name="Invitee",
        )
        accept_response = client.post(
            "/invitations/accept",
            json={"token": raw_token},
            headers=auth_headers(invitee_token),
        )
        assert accept_response.status_code == 401
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(invitee_email)


@pytest.mark.anyio
async def test_revoke_is_idempotent() -> None:
    owner_email = "endpoint-test-inv-revoke-owner-2@example.com"
    org_id, headers = await _new_org(owner_email)
    try:
        _raw_token, invitation_id = await _new_invitation(
            org_id, "someone@example.com", role_name="viewer"
        )

        first = client.delete(
            f"/organizations/{org_id}/invitations/{invitation_id}", headers=headers
        )
        assert first.status_code == 204
        second = client.delete(
            f"/organizations/{org_id}/invitations/{invitation_id}", headers=headers
        )
        assert second.status_code == 204
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)


@pytest.mark.anyio
async def test_revoke_accepted_invitation_returns_409() -> None:
    owner_email = "endpoint-test-inv-revoke-owner-3@example.com"
    invitee_email = "endpoint-test-inv-revoke-invitee-3@example.com"
    org_id, headers = await _new_org(owner_email)
    try:
        raw_token, invitation_id = await _new_invitation(org_id, invitee_email, role_name="viewer")
        invitee_token = signup_and_login(
            client,
            email=invitee_email,
            password="correct horse battery staple",
            full_name="Invitee",
        )
        client.post(
            "/invitations/accept",
            json={"token": raw_token},
            headers=auth_headers(invitee_token),
        )

        response = client.delete(
            f"/organizations/{org_id}/invitations/{invitation_id}", headers=headers
        )
        assert response.status_code == 409
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(invitee_email)


@pytest.mark.anyio
async def test_revoke_nonexistent_invitation_returns_404() -> None:
    owner_email = "endpoint-test-inv-revoke-owner-4@example.com"
    org_id, headers = await _new_org(owner_email)
    try:
        response = client.delete(
            f"/organizations/{org_id}/invitations/{uuid.uuid4()}", headers=headers
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)


@pytest.mark.anyio
async def test_revoke_invitation_is_audited() -> None:
    owner_email = "endpoint-test-inv-revoke-owner-5@example.com"
    org_id, headers = await _new_org(owner_email)
    try:
        _raw_token, invitation_id = await _new_invitation(
            org_id, "someone@example.com", role_name="viewer"
        )
        client.delete(f"/organizations/{org_id}/invitations/{invitation_id}", headers=headers)

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(AuditLog).where(AuditLog.resource_id == invitation_id)
            )
            logs = result.scalars().all()
            assert [log.action for log in logs] == ["invitation.revoke"]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
