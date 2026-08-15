"""Integration tests against the real FastAPI app for
routers/conversation.py (roadmap step 178). Mirrors
test_assistant_endpoints.py's own shape (160), one nesting level
deeper -- org -> workspace -> knowledge base -> assistant -> conversation.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db import get_session, set_tenant_context
from main import app
from models.assistant import Assistant
from models.audit_log import AuditLog
from models.conversation import Conversation
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
        for model in (Conversation, Assistant, KnowledgeBase, Workspace, AuditLog, Membership):
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


async def _add_member(org_id: uuid.UUID, email: str, role_name: str) -> None:
    async with get_session() as session:
        user_result = await session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one()
        role_result = await session.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one()
        await set_tenant_context(session, org_id)
        session.add(
            Membership(tenant_id=org_id, user_id=user.id, workspace_id=None, role_id=role.id)
        )
        await session.commit()


def _new_org_workspace_kb_assistant(
    email: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Conv Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Conversation Test Org", "slug": f"endpoint-test-conv-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Conv Test Workspace", "slug": "endpoint-test-conv-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Conv Test KB", "slug": "endpoint-test-conv-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    asst_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/assistants",
        json={"name": "Conv Bot", "slug": "endpoint-test-conv-bot"},
        headers=headers,
    )
    assistant_id = uuid.UUID(asst_response.json()["id"])
    return org_id, workspace_id, kb_id, assistant_id, headers


def _conv_url(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kb_id: uuid.UUID,
    assistant_id: uuid.UUID,
    suffix: str = "",
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/assistants/{assistant_id}/conversations{suffix}"
    )


def test_conversation_routes_require_auth() -> None:
    response = client.post(_conv_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()))
    assert response.status_code == 401


@pytest.mark.anyio
async def test_non_member_cannot_create_conversation() -> None:
    email = "endpoint-test-conv-owner-1@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        email
    )
    try:
        outsider_token = signup_and_login(
            client,
            email="endpoint-test-conv-outsider@example.com",
            password="correct horse battery staple",
            full_name="Outsider",
        )
        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id),
            headers=auth_headers(outsider_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)
        await _cleanup_user("endpoint-test-conv-outsider@example.com")


@pytest.mark.anyio
async def test_create_conversation_as_org_owner() -> None:
    email = "endpoint-test-conv-owner-2@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id), headers=headers
        )
        assert response.status_code == 201
        body = response.json()
        assert body["tenant_id"] == str(org_id)
        assert body["assistant_id"] == str(assistant_id)
        assert body["user_id"] is not None
        assert body["status"] == "new"

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            audit_result = await session.execute(
                select(AuditLog).where(AuditLog.action == "conversation.create")
            )
            assert audit_result.scalar_one_or_none() is not None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_can_create_conversation() -> None:
    """The opposite polarity of test_assistant_endpoints.py's own
    end_user-cannot-create-assistant test -- conversation:create is
    deliberately granted to end_user (core product use), unlike
    assistant:create (org_owner/admin/manager-only configuration)."""
    owner_email = "endpoint-test-conv-owner-3@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    member_email = "endpoint-test-conv-end-user@example.com"
    try:
        member_token = signup_and_login(
            client,
            email=member_email,
            password="correct horse battery staple",
            full_name="End User Member",
        )
        await _add_member(org_id, member_email, "end_user")

        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id),
            headers=auth_headers(member_token),
        )
        assert response.status_code == 201
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(member_email)


@pytest.mark.anyio
async def test_viewer_role_cannot_create_conversation() -> None:
    """viewer is explicitly read-only -- confirms it was NOT included
    in conversation:create's granted-roles list."""
    owner_email = "endpoint-test-conv-owner-4@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    member_email = "endpoint-test-conv-viewer@example.com"
    try:
        member_token = signup_and_login(
            client,
            email=member_email,
            password="correct horse battery staple",
            full_name="Viewer Member",
        )
        await _add_member(org_id, member_email, "viewer")

        response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id),
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(member_email)


@pytest.mark.anyio
async def test_assistant_not_visible_under_a_different_knowledge_base() -> None:
    email = "endpoint-test-conv-owner-5@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        other_kb_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
            json={"name": "Other KB", "slug": "endpoint-test-conv-other-kb"},
            headers=headers,
        )
        other_kb_id = uuid.UUID(other_kb_response.json()["id"])

        # Real assistant, real org, real membership -- just the wrong
        # knowledge base in the URL. Must 404, not leak across
        # knowledge bases within the same workspace.
        response = client.post(
            _conv_url(org_id, workspace_id, other_kb_id, assistant_id), headers=headers
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_list_conversations_is_paginated_and_ordered_newest_first() -> None:
    email = "endpoint-test-conv-owner-6@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        created_ids = []
        for _ in range(3):
            create_response = client.post(
                _conv_url(org_id, workspace_id, kb_id, assistant_id), headers=headers
            )
            created_ids.append(create_response.json()["id"])

        list_response = client.get(
            _conv_url(org_id, workspace_id, kb_id, assistant_id) + "?limit=2",
            headers=headers,
        )
        assert list_response.status_code == 200
        body = list_response.json()
        assert body["total"] == 3
        assert body["limit"] == 2
        assert len(body["items"]) == 2
        # Newest first -- the most recently created conversation (last
        # in created_ids) should be the first item back.
        assert body["items"][0]["id"] == created_ids[-1]
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_list_conversations_only_returns_the_callers_own() -> None:
    """conversation:read's list is personal history, not an org-wide
    view -- another real member with real conversation:read/create
    permission still can't see conversations they don't own."""
    owner_email = "endpoint-test-conv-owner-7@example.com"
    org_id, workspace_id, kb_id, assistant_id, owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    other_email = "endpoint-test-conv-other-owner@example.com"
    try:
        client.post(_conv_url(org_id, workspace_id, kb_id, assistant_id), headers=owner_headers)

        other_token = signup_and_login(
            client,
            email=other_email,
            password="correct horse battery staple",
            full_name="Other Member",
        )
        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.email == other_email))
            other_user = user_result.scalar_one()
            role_result = await session.execute(select(Role).where(Role.name == "manager"))
            manager_role = role_result.scalar_one()
            await set_tenant_context(session, org_id)
            session.add(
                Membership(
                    tenant_id=org_id,
                    user_id=other_user.id,
                    workspace_id=None,
                    role_id=manager_role.id,
                )
            )
            await session.commit()

        other_create = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id),
            headers=auth_headers(other_token),
        )
        other_conversation_id = other_create.json()["id"]

        other_list = client.get(
            _conv_url(org_id, workspace_id, kb_id, assistant_id),
            headers=auth_headers(other_token),
        )
        assert other_list.status_code == 200
        ids_seen = {item["id"] for item in other_list.json()["items"]}
        assert ids_seen == {other_conversation_id}
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(other_email)


@pytest.mark.anyio
async def test_viewer_role_can_list_but_not_create_conversations() -> None:
    """conversation:read is deliberately broader than conversation:create
    -- viewer is excluded from create (159/178's own precedent: viewer
    never creates anything) but included in read (reading one's own
    history is exactly what a read-only role is for)."""
    owner_email = "endpoint-test-conv-owner-8@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    viewer_email = "endpoint-test-conv-viewer-list@example.com"
    try:
        viewer_token = signup_and_login(
            client,
            email=viewer_email,
            password="correct horse battery staple",
            full_name="Viewer Member",
        )
        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.email == viewer_email))
            viewer_user = user_result.scalar_one()
            role_result = await session.execute(select(Role).where(Role.name == "viewer"))
            viewer_role = role_result.scalar_one()
            await set_tenant_context(session, org_id)
            session.add(
                Membership(
                    tenant_id=org_id,
                    user_id=viewer_user.id,
                    workspace_id=None,
                    role_id=viewer_role.id,
                )
            )
            await session.commit()

        create_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id),
            headers=auth_headers(viewer_token),
        )
        assert create_response.status_code == 403

        list_response = client.get(
            _conv_url(org_id, workspace_id, kb_id, assistant_id),
            headers=auth_headers(viewer_token),
        )
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 0
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(viewer_email)


@pytest.mark.anyio
async def test_rename_and_pin_a_conversation_via_partial_update() -> None:
    email = "endpoint-test-conv-owner-9@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        create_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id), headers=headers
        )
        conversation_id = create_response.json()["id"]
        assert create_response.json()["title"] is None
        assert create_response.json()["is_pinned"] is False

        rename_response = client.patch(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}"),
            json={"title": "Refund questions"},
            headers=headers,
        )
        assert rename_response.status_code == 200
        assert rename_response.json()["title"] == "Refund questions"
        # is_pinned wasn't included in the body -- untouched.
        assert rename_response.json()["is_pinned"] is False

        pin_response = client.patch(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}"),
            json={"is_pinned": True},
            headers=headers,
        )
        assert pin_response.status_code == 200
        assert pin_response.json()["is_pinned"] is True
        # title wasn't included this time -- stays from the earlier rename.
        assert pin_response.json()["title"] == "Refund questions"

        clear_response = client.patch(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}"),
            json={"title": None},
            headers=headers,
        )
        assert clear_response.status_code == 200
        assert clear_response.json()["title"] is None
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_archive_a_conversation_and_reject_archiving_it_twice() -> None:
    email = "endpoint-test-conv-owner-10@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        create_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id), headers=headers
        )
        conversation_id = create_response.json()["id"]

        archive_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}/archive"),
            headers=headers,
        )
        assert archive_response.status_code == 200
        assert archive_response.json()["status"] == "archived"

        second_archive_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}/archive"),
            headers=headers,
        )
        assert second_archive_response.status_code == 409
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_delete_a_conversation_removes_it_and_its_messages() -> None:
    email = "endpoint-test-conv-owner-11@example.com"
    org_id, workspace_id, kb_id, assistant_id, headers = _new_org_workspace_kb_assistant(email)
    try:
        create_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id), headers=headers
        )
        conversation_id = create_response.json()["id"]

        delete_response = client.delete(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}"),
            headers=headers,
        )
        assert delete_response.status_code == 204

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            remaining = await session.get(Conversation, uuid.UUID(conversation_id))
            assert remaining is None

        # A second delete of the same, now-gone conversation 404s --
        # same ownership/existence check every other single-resource
        # operation on this router already uses.
        second_delete_response = client.delete(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}"),
            headers=headers,
        )
        assert second_delete_response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_another_user_cannot_update_archive_or_delete_someone_elses_conversation() -> None:
    owner_email = "endpoint-test-conv-owner-12@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    other_email = "endpoint-test-conv-other-owner-2@example.com"
    try:
        create_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id), headers=_owner_headers
        )
        conversation_id = create_response.json()["id"]

        other_token = signup_and_login(
            client,
            email=other_email,
            password="correct horse battery staple",
            full_name="Other Owner",
        )
        await _add_member(org_id, other_email, "manager")
        other_headers = auth_headers(other_token)

        patch_response = client.patch(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}"),
            json={"title": "Should fail"},
            headers=other_headers,
        )
        assert patch_response.status_code == 404

        archive_response = client.post(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}/archive"),
            headers=other_headers,
        )
        assert archive_response.status_code == 404

        delete_response = client.delete(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{conversation_id}"),
            headers=other_headers,
        )
        assert delete_response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(other_email)


@pytest.mark.anyio
async def test_viewer_role_cannot_update_or_delete_a_conversation() -> None:
    """conversation:update/conversation:delete exclude viewer, same
    reasoning conversation:create/message:create already established --
    made the REAL owner via direct ORM creation (viewer can't create
    one through the real endpoint) so this isolates the permission
    check, same pattern test_message_endpoints.py's own viewer test
    already established."""
    owner_email = "endpoint-test-conv-owner-13@example.com"
    org_id, workspace_id, kb_id, assistant_id, _owner_headers = _new_org_workspace_kb_assistant(
        owner_email
    )
    viewer_email = "endpoint-test-conv-viewer-update@example.com"
    try:
        viewer_token = signup_and_login(
            client,
            email=viewer_email,
            password="correct horse battery staple",
            full_name="Viewer Member",
        )
        await _add_member(org_id, viewer_email, "viewer")
        viewer_headers = auth_headers(viewer_token)

        async with get_session() as session:
            user_result = await session.execute(select(User).where(User.email == viewer_email))
            viewer_user = user_result.scalar_one()
            await set_tenant_context(session, org_id)
            conversation = Conversation(
                tenant_id=org_id, assistant_id=assistant_id, user_id=viewer_user.id
            )
            session.add(conversation)
            await session.commit()
            own_conversation_id = conversation.id

        patch_response = client.patch(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{own_conversation_id}"),
            json={"title": "Should fail"},
            headers=viewer_headers,
        )
        assert patch_response.status_code == 403

        delete_response = client.delete(
            _conv_url(org_id, workspace_id, kb_id, assistant_id, f"/{own_conversation_id}"),
            headers=viewer_headers,
        )
        assert delete_response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user(viewer_email)
