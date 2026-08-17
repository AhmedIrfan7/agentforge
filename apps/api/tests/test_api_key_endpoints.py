"""Integration tests against the real FastAPI app for routers/api_key.py
(roadmap step 241 -- API-key management UI + endpoints, no prior
backend existed for this resource at all).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.api_key import ApiKey
from models.audit_log import AuditLog
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.session import Session
from models.user import User
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (ApiKey, AuditLog, Membership):
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
        client, email=email, password="correct horse battery staple", full_name="API Key Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "API Key Test Org", "slug": f"endpoint-test-apikey-org-{local_part}"},
        headers=headers,
    )
    return uuid.UUID(org_response.json()["id"]), headers


@pytest.mark.anyio
async def test_create_api_key_returns_the_raw_key_exactly_once() -> None:
    email = "endpoint-test-apikey-owner-1@example.com"
    org_id, headers = _new_org(email)
    try:
        response = client.post(
            f"/organizations/{org_id}/api-keys", json={"name": "CI key"}, headers=headers
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "CI key"
        assert body["key"].startswith("afk_live_")
        assert body["key_prefix"] == body["key"][:12]
        # The list endpoint (below) never carries "key" -- prove the
        # create response is the ONLY place it ever appears.
        list_response = client.get(f"/organizations/{org_id}/api-keys", headers=headers)
        list_item = list_response.json()["items"][0]
        assert "key" not in list_item
        assert "key_hash" not in list_item
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_list_api_keys_shows_name_prefix_and_revoked_state() -> None:
    email = "endpoint-test-apikey-owner-2@example.com"
    org_id, headers = _new_org(email)
    try:
        client.post(f"/organizations/{org_id}/api-keys", json={"name": "Prod key"}, headers=headers)
        response = client.get(f"/organizations/{org_id}/api-keys", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Prod key"
        assert body["items"][0]["revoked_at"] is None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_revoke_api_key_is_idempotent() -> None:
    email = "endpoint-test-apikey-owner-3@example.com"
    org_id, headers = _new_org(email)
    try:
        create_response = client.post(
            f"/organizations/{org_id}/api-keys", json={"name": "Throwaway key"}, headers=headers
        )
        api_key_id = create_response.json()["id"]

        first_revoke = client.delete(
            f"/organizations/{org_id}/api-keys/{api_key_id}", headers=headers
        )
        assert first_revoke.status_code == 204

        second_revoke = client.delete(
            f"/organizations/{org_id}/api-keys/{api_key_id}", headers=headers
        )
        assert second_revoke.status_code == 204

        list_response = client.get(f"/organizations/{org_id}/api-keys", headers=headers)
        assert list_response.json()["items"][0]["revoked_at"] is not None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_revoke_nonexistent_api_key_returns_404() -> None:
    email = "endpoint-test-apikey-owner-4@example.com"
    org_id, headers = _new_org(email)
    try:
        response = client.delete(
            f"/organizations/{org_id}/api-keys/{uuid.uuid4()}", headers=headers
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_create_list_or_revoke_api_keys() -> None:
    owner_email = "endpoint-test-apikey-owner-5@example.com"
    org_id, owner_headers = _new_org(owner_email)
    end_user_email = "endpoint-test-apikey-enduser@example.com"
    try:
        create_response = client.post(
            f"/organizations/{org_id}/api-keys", json={"name": "Owner's key"}, headers=owner_headers
        )
        api_key_id = create_response.json()["id"]

        end_user_token = signup_and_login(
            client,
            email=end_user_email,
            password="correct horse battery staple",
            full_name="End User",
        )
        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == end_user_email))
            end_user = result.scalar_one()
            role_result = await session.execute(select(Role).where(Role.name == "end_user"))
            end_user_role = role_result.scalar_one()
            await set_tenant_context(session, org_id)
            session.add(
                Membership(
                    tenant_id=org_id,
                    user_id=end_user.id,
                    workspace_id=None,
                    role_id=end_user_role.id,
                )
            )
            await session.commit()
        end_user_headers = auth_headers(end_user_token)

        assert (
            client.post(
                f"/organizations/{org_id}/api-keys", json={"name": "Nope"}, headers=end_user_headers
            ).status_code
            == 403
        )
        assert (
            client.get(f"/organizations/{org_id}/api-keys", headers=end_user_headers).status_code
            == 403
        )
        assert (
            client.delete(
                f"/organizations/{org_id}/api-keys/{api_key_id}", headers=end_user_headers
            ).status_code
            == 403
        )
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(end_user_email)
