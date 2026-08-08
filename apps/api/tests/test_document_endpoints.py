"""Integration tests against the real FastAPI app for
routers/document.py (roadmap step 084).

Uploads go through the real endpoint to real MinIO (already required
local infra, same as Postgres and Redis — see docker-compose.yml) rather
than a faked storage client. Unlike Google's OAuth API (steps 076-077),
MinIO is infrastructure this project owns and already runs in CI
(.github/workflows/api-tests.yml), so there's no reason to abstract it
away in tests the way a genuine third-party dependency would need to be.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from config import settings
from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.session import Session
from models.user import User
from models.workspace import Workspace
from storage import _client_context
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Document, KnowledgeBase, Workspace, AuditLog, Membership):
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


async def _cleanup_storage(storage_key: str) -> None:
    async with _client_context() as s3:
        await s3.delete_object(Bucket="agentforge-dev", Key=storage_key)


def _new_org_with_kb(email: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="Doc Test"
    )
    headers = auth_headers(token)
    local_part = email.split("@", 1)[0]
    org_response = client.post(
        "/organizations",
        json={"name": "Doc Test Org", "slug": f"endpoint-test-doc-org-{local_part}"},
        headers=headers,
    )
    org_id = uuid.UUID(org_response.json()["id"])
    ws_response = client.post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Doc Test Workspace", "slug": "endpoint-test-doc-ws"},
        headers=headers,
    )
    workspace_id = uuid.UUID(ws_response.json()["id"])
    kb_response = client.post(
        f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
        json={"name": "Doc Test KB", "slug": "endpoint-test-doc-kb"},
        headers=headers,
    )
    kb_id = uuid.UUID(kb_response.json()["id"])
    return org_id, workspace_id, kb_id, headers


def _docs_url(
    org_id: uuid.UUID, workspace_id: uuid.UUID, kb_id: uuid.UUID, suffix: str = ""
) -> str:
    return (
        f"/organizations/{org_id}/workspaces/{workspace_id}"
        f"/knowledge-bases/{kb_id}/documents{suffix}"
    )


def test_document_routes_require_auth() -> None:
    response = client.get(_docs_url(uuid.uuid4(), uuid.uuid4(), uuid.uuid4()))
    assert response.status_code == 401


@pytest.mark.anyio
async def test_non_member_cannot_upload_document() -> None:
    org_id, workspace_id, kb_id, _owner_headers = _new_org_with_kb(
        "endpoint-test-doc-owner-1@example.com"
    )
    try:
        outsider_token = signup_and_login(
            client,
            email="endpoint-test-doc-outsider@example.com",
            password="correct horse battery staple",
            full_name="Outsider",
        )
        response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", b"hello", "text/plain")},
            headers=auth_headers(outsider_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user("endpoint-test-doc-owner-1@example.com")
        await _cleanup_user("endpoint-test-doc-outsider@example.com")


@pytest.mark.anyio
async def test_upload_document_as_org_owner_stores_in_minio() -> None:
    email = "endpoint-test-doc-owner-2@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        content = b"Employee handbook contents go here."
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("handbook.txt", content, "text/plain")},
            headers=headers,
        )
        assert upload_response.status_code == 201
        body = upload_response.json()
        document_id = body["id"]
        assert body["tenant_id"] == str(org_id)
        assert body["knowledge_base_id"] == str(kb_id)
        assert body["title"] == "handbook.txt"
        assert body["status"] == "pending"
        assert body["content_type"] == "text/plain"
        assert body["size_bytes"] == len(content)
        assert "storage_key" not in body  # internal detail, never exposed

        # The Document row exists, but so does the actual object in
        # MinIO -- prove both, not just the DB half.
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key

        async with _client_context() as s3:
            stored = await s3.get_object(Bucket="agentforge-dev", Key=storage_key)
            stored_body = await stored["Body"].read()
            assert stored_body == content

        get_response = client.get(
            _docs_url(org_id, workspace_id, kb_id, f"/{document_id}"), headers=headers
        )
        assert get_response.status_code == 200

        list_response = client.get(_docs_url(org_id, workspace_id, kb_id), headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_upload_document() -> None:
    owner_email = "endpoint-test-doc-owner-3@example.com"
    org_id, workspace_id, kb_id, _owner_headers = _new_org_with_kb(owner_email)
    try:
        member_token = signup_and_login(
            client,
            email="endpoint-test-doc-member@example.com",
            password="correct horse battery staple",
            full_name="End User Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-doc-member@example.com")
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
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", b"hello", "text/plain")},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-doc-member@example.com")


@pytest.mark.anyio
async def test_document_not_visible_under_a_different_knowledge_base() -> None:
    email = "endpoint-test-doc-owner-4@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("scoped.txt", b"scoped content", "text/plain")},
            headers=headers,
        )
        document_id = upload_response.json()["id"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key

        other_kb_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
            json={"name": "Other KB", "slug": "endpoint-test-doc-other-kb"},
            headers=headers,
        )
        other_kb_id = uuid.UUID(other_kb_response.json()["id"])

        response = client.get(
            _docs_url(org_id, workspace_id, other_kb_id, f"/{document_id}"), headers=headers
        )
        assert response.status_code == 404
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_upload_rejects_disallowed_file_type() -> None:
    """validation.py (step 085) is actually wired into the real
    endpoint, not just correct in isolation (see test_validation.py for
    the full extension/content-signature matrix)."""
    email = "endpoint-test-doc-owner-5@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

        # Nothing should have been created for a rejected upload.
        list_response = client.get(_docs_url(org_id, workspace_id, kb_id), headers=headers)
        assert list_response.json()["total"] == 0
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_upload_rejects_content_that_does_not_match_its_extension() -> None:
    email = "endpoint-test-doc-owner-6@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("fake.pdf", b"just plain text, not a real PDF", "application/pdf")},
            headers=headers,
        )
        assert response.status_code == 422
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_upload_rejects_file_over_the_configured_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validation.py's size check (step 086) is actually wired into the
    real endpoint. Monkeypatches the limit down to a few bytes instead of
    actually transferring settings.max_upload_size_bytes (50 MB) worth
    of data through TestClient just to trip it."""

    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)

    email = "endpoint-test-doc-owner-7@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", b"this is way more than ten bytes", "text/plain")},
            headers=headers,
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "file_too_large"

        list_response = client.get(_docs_url(org_id, workspace_id, kb_id), headers=headers)
        assert list_response.json()["total"] == 0
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_upload_at_exactly_the_size_limit_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)

    email = "endpoint-test-doc-owner-8@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        content = b"exactly10b"
        assert len(content) == 10
        response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", content, "text/plain")},
            headers=headers,
        )
        assert response.status_code == 201

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(response.json()["id"]))
            assert document is not None
            storage_key = document.storage_key
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)
