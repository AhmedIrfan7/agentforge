"""Integration tests against the real FastAPI app for
routers/assistant.py (roadmap step 160). Mirrors
test_knowledge_base_endpoints.py's own shape (082), one nesting level
deeper -- org -> workspace -> knowledge base -> assistant.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.assistant import Assistant
from models.audit_log import AuditLog
from models.knowledge_base import KnowledgeBase
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
        for model in (Assistant, KnowledgeBase, Workspace, AuditLog, Membership):
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


def _new_org_workspace_kb(email: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Assistant Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Assistant Test Org", "slug": f"endpoint-test-asst-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Assistant Test Workspace", "slug": "endpoint-test-asst-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Assistant Test KB", "slug": "endpoint-test-asst-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    return org_id, workspace_id, kb_id, headers


def _asst_url(
    org_id: uuid.UUID, workspace_id: uuid.UUID, kb_id: uuid.UUID, suffix: str = ""
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants{suffix}"
    )


def test_assistant_routes_require_auth() -> None:
    response = client.get(_asst_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4()))
    assert response.status_code == 401


@pytest.mark.anyio
async def test_non_member_cannot_access_assistants() -> None:
    org_id, workspace_id, kb_id, _owner_headers = _new_org_workspace_kb(
        "endpoint-test-asst-owner-1@example.com"
    )
    try:
        outsider_token = signup_and_login(
            client,
            email="endpoint-test-asst-outsider@example.com",
            password="correct horse battery staple",
            full_name="Outsider",
        )
        response = client.get(
            _asst_url(org_id, workspace_id, kb_id), headers=auth_headers(outsider_token)
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user("endpoint-test-asst-owner-1@example.com")
        await _cleanup_user("endpoint-test-asst-outsider@example.com")


@pytest.mark.anyio
async def test_assistant_crud_as_org_owner() -> None:
    email = "endpoint-test-asst-owner-2@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        create_response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={
                "name": "Support Bot",
                "slug": "endpoint-test-asst",
                "description": "Answers questions.",
                "agent_configuration": {
                    "llm_provider": "anthropic",
                    "enabled_agents": ["retriever", "citation"],
                    "retrieval_top_k": 20,
                },
            },
            headers=headers,
        )
        assert create_response.status_code == 201
        body = create_response.json()
        assistant_id = body["id"]
        assert body["tenant_id"] == str(org_id)
        assert body["knowledge_base_id"] == str(kb_id)
        assert body["description"] == "Answers questions."
        assert body["agent_configuration"] == {
            "llm_provider": "anthropic",
            "enabled_agents": ["retriever", "citation"],
            "retrieval_top_k": 20,
        }
        # Not requested in the body -- defaults closed (step 192).
        assert body["is_public"] is False

        get_response = client.get(
            _asst_url(org_id, workspace_id, kb_id, f"/{assistant_id}"), headers=headers
        )
        assert get_response.status_code == 200

        list_response = client.get(_asst_url(org_id, workspace_id, kb_id), headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        delete_response = client.delete(
            _asst_url(org_id, workspace_id, kb_id, f"/{assistant_id}"), headers=headers
        )
        assert delete_response.status_code == 204

        after_delete = client.get(
            _asst_url(org_id, workspace_id, kb_id, f"/{assistant_id}"), headers=headers
        )
        assert after_delete.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_create_assistant_defaults_agent_configuration_when_omitted() -> None:
    email = "endpoint-test-asst-owner-3@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        create_response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "Default Bot", "slug": "endpoint-test-asst-default"},
            headers=headers,
        )
        assert create_response.status_code == 201
        assert create_response.json()["agent_configuration"] == {
            "llm_provider": "openai",
            "enabled_agents": ["retriever"],
            "retrieval_top_k": 10,
        }
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_create_assistant_can_opt_in_to_public_anonymous_access() -> None:
    email = "endpoint-test-asst-owner-public@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        create_response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "Public Bot", "slug": "endpoint-test-asst-public", "is_public": True},
            headers=headers,
        )
        assert create_response.status_code == 201
        assert create_response.json()["is_public"] is True
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_create_assistant_rejects_an_invalid_agent_configuration() -> None:
    email = "endpoint-test-asst-owner-4@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={
                "name": "Bad Bot",
                "slug": "endpoint-test-asst-bad",
                "agent_configuration": {"llm_provider": "not-a-real-provider"},
            },
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_create_assistant() -> None:
    owner_email = "endpoint-test-asst-owner-5@example.com"
    org_id, workspace_id, kb_id, _owner_headers = _new_org_workspace_kb(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-asst-member@example.com",
            password="correct horse battery staple",
            full_name="End User Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-asst-member@example.com")
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
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "Should Fail", "slug": "endpoint-test-asst-should-fail"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-asst-member@example.com")


@pytest.mark.anyio
async def test_assistant_not_visible_under_a_different_knowledge_base() -> None:
    email = "endpoint-test-asst-owner-6@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        create_response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "Scoped Bot", "slug": "endpoint-test-asst-scoped"},
            headers=headers,
        )
        assistant_id = create_response.json()["id"]

        other_kb_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
            json={"name": "Other KB", "slug": "endpoint-test-asst-other-kb"},
            headers=headers,
        )
        other_kb_id = uuid.UUID(other_kb_response.json()["id"])

        # Real assistant, real org, real membership -- just the wrong
        # knowledge base in the URL. Must 404, not leak across
        # knowledge bases within the same workspace.
        response = client.get(
            _asst_url(org_id, workspace_id, other_kb_id, f"/{assistant_id}"), headers=headers
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_duplicate_slug_within_knowledge_base_conflicts_but_other_kb_ok() -> None:
    email = "endpoint-test-asst-owner-7@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        first = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "First", "slug": "endpoint-test-asst-dup"},
            headers=headers,
        )
        assert first.status_code == 201

        duplicate = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "Second", "slug": "endpoint-test-asst-dup"},
            headers=headers,
        )
        assert duplicate.status_code == 409

        other_kb_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
            json={"name": "Sibling KB", "slug": "endpoint-test-asst-sibling-kb"},
            headers=headers,
        )
        other_kb_id = uuid.UUID(other_kb_response.json()["id"])

        same_slug_other_kb = client.post(
            _asst_url(org_id, workspace_id, other_kb_id),
            json={"name": "Same Slug Elsewhere", "slug": "endpoint-test-asst-dup"},
            headers=headers,
        )
        assert same_slug_other_kb.status_code == 201
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_update_assistant_is_a_real_partial_update() -> None:
    email = "endpoint-test-asst-update-1@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        create_response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={
                "name": "Original Name",
                "slug": "endpoint-test-asst-update",
                "description": "Original description.",
            },
            headers=headers,
        )
        assistant_id = create_response.json()["id"]
        assert create_response.json()["instructions"] is None

        # Only instructions -- name/description must stay untouched.
        first_response = client.patch(
            _asst_url(org_id, workspace_id, kb_id, f"/{assistant_id}"),
            json={"instructions": "Always cite your sources."},
            headers=headers,
        )
        assert first_response.status_code == 200
        body = first_response.json()
        assert body["instructions"] == "Always cite your sources."
        assert body["name"] == "Original Name"
        assert body["description"] == "Original description."

        # Only name -- instructions set moments ago must survive.
        second_response = client.patch(
            _asst_url(org_id, workspace_id, kb_id, f"/{assistant_id}"),
            json={"name": "Renamed"},
            headers=headers,
        )
        assert second_response.status_code == 200
        body = second_response.json()
        assert body["name"] == "Renamed"
        assert body["instructions"] == "Always cite your sources."
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_update_assistant_agent_configuration_and_is_public() -> None:
    email = "endpoint-test-asst-update-2@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        create_response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "Config Bot", "slug": "endpoint-test-asst-update-config"},
            headers=headers,
        )
        assistant_id = create_response.json()["id"]
        assert create_response.json()["is_public"] is False

        response = client.patch(
            _asst_url(org_id, workspace_id, kb_id, f"/{assistant_id}"),
            json={
                "agent_configuration": {
                    "llm_provider": "anthropic",
                    "enabled_agents": ["retriever", "citation"],
                    "retrieval_top_k": 25,
                },
                "is_public": True,
            },
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["agent_configuration"] == {
            "llm_provider": "anthropic",
            "enabled_agents": ["retriever", "citation"],
            "retrieval_top_k": 25,
        }
        assert body["is_public"] is True
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_explicitly_nulling_assistant_name_returns_422() -> None:
    email = "endpoint-test-asst-update-3@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        create_response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "Null Name Test", "slug": "endpoint-test-asst-update-null"},
            headers=headers,
        )
        assistant_id = create_response.json()["id"]

        response = client.patch(
            _asst_url(org_id, workspace_id, kb_id, f"/{assistant_id}"),
            json={"name": None},
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_update_nonexistent_assistant_returns_404() -> None:
    email = "endpoint-test-asst-update-4@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(email)
    try:
        response = client.patch(
            _asst_url(org_id, workspace_id, kb_id, f"/{uuid.uuid4()}"),
            json={"name": "Doesn't Matter"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_update_assistant() -> None:
    owner_email = "endpoint-test-asst-update-owner@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_workspace_kb(owner_email)
    try:
        create_response = client.post(
            _asst_url(org_id, workspace_id, kb_id),
            json={"name": "Protected Bot", "slug": "endpoint-test-asst-update-protected"},
            headers=headers,
        )
        assistant_id = create_response.json()["id"]

        member_token = signup_and_login(
            client,
            email="endpoint-test-asst-update-member@example.com",
            password="correct horse battery staple",
            full_name="End User Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-asst-update-member@example.com")
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

        response = client.patch(
            _asst_url(org_id, workspace_id, kb_id, f"/{assistant_id}"),
            json={"name": "Hijacked Name"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-asst-update-member@example.com")
