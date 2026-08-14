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
async def test_upload_dispatches_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """extraction.py:dispatch_extraction (step 090) is actually called by
    the real endpoint, with the right document/tenant ids -- its own
    routing/status-transition logic is covered separately in
    test_extraction.py against real Postgres/MinIO, so this only needs
    to prove the wiring, not re-run that logic. Monkeypatches .delay
    itself rather than letting a real task hit the broker: nothing here
    needs (or should depend on) a live worker actually consuming it."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "routers.document.dispatch_extraction.delay",
        lambda document_id, tenant_id: calls.append((document_id, tenant_id)),
    )

    email = "endpoint-test-doc-owner-13@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("dispatch-me.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = upload_response.json()["id"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key

        assert calls == [(document_id, str(org_id))]
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_get_document_status_returns_status_and_updated_at() -> None:
    """Roadmap step 088's polling endpoint -- a smaller view of the same
    document, not a new capability (see test_document_status_requires_
    document_read_not_a_new_permission below)."""
    email = "endpoint-test-doc-owner-10@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("status-check.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = upload_response.json()["id"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key

        response = client.get(
            _docs_url(org_id, workspace_id, kb_id, f"/{document_id}/status"), headers=headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == document_id
        assert body["status"] == "pending"
        assert set(body.keys()) == {"id", "status", "updated_at"}  # not the full document
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_document_status_not_visible_under_a_different_knowledge_base() -> None:
    email = "endpoint-test-doc-owner-11@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("scoped-status.txt", b"content", "text/plain")},
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
            json={"name": "Other Status KB", "slug": "endpoint-test-doc-status-other-kb"},
            headers=headers,
        )
        other_kb_id = uuid.UUID(other_kb_response.json()["id"])

        response = client.get(
            _docs_url(org_id, workspace_id, other_kb_id, f"/{document_id}/status"), headers=headers
        )
        assert response.status_code == 404
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_poll_document_status() -> None:
    """document:read (same permission the full GET already requires) --
    proves this isn't a new, unguarded capability."""
    owner_email = "endpoint-test-doc-owner-12@example.com"
    org_id, workspace_id, kb_id, owner_headers = _new_org_with_kb(owner_email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("guarded.txt", b"content", "text/plain")},
            headers=owner_headers,
        )
        document_id = upload_response.json()["id"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key

        member_token = signup_and_login(
            client,
            email="endpoint-test-doc-status-member@example.com",
            password="correct horse battery staple",
            full_name="Status Poll Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-doc-status-member@example.com")
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
            _docs_url(org_id, workspace_id, kb_id, f"/{document_id}/status"),
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-doc-status-member@example.com")


@pytest.mark.anyio
async def test_upload_rejects_infected_file() -> None:
    """antivirus.py's scan (step 087) is actually wired into the real
    endpoint, not just correct in isolation (see test_antivirus.py). Uses
    the standard EICAR test string -- a harmless file every antivirus
    engine, including ClamAV, is guaranteed to flag as a virus."""
    eicar = (r"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*").encode(
        "ascii"
    )
    email = "endpoint-test-doc-owner-9@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("eicar.txt", eicar, "text/plain")},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "infected_file"

        list_response = client.get(_docs_url(org_id, workspace_id, kb_id), headers=headers)
        assert list_response.json()["total"] == 0
    finally:
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


@pytest.mark.anyio
async def test_override_chunking_strategy_with_no_recommendation_yet() -> None:
    """No worker runs during pytest (roadmap step 089's own test split),
    so a just-uploaded document's doc_metadata never gains a real
    chunking_recommendation here -- this is the genuinely common case
    the endpoint has to handle honestly: a caller can still set a
    strategy before extraction has ever run, and it's correctly recorded
    as an override with no recommendation to compare against."""
    email = "endpoint-test-doc-owner-14@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = upload_response.json()["id"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key

        response = client.patch(
            _docs_url(org_id, workspace_id, kb_id, f"/{document_id}/chunking-strategy"),
            json={"strategy": "table_aware"},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["strategy"] == "table_aware"
        assert body["source"] == "override"
        assert "no recommendation existed yet" in body["reasoning"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            fetched = await session.get(Document, uuid.UUID(document_id))
            assert fetched is not None
            assert fetched.chunking_strategy == "table_aware"
            assert fetched.chunking_strategy_source == "override"
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_override_chunking_strategy_matching_recommendation_is_accepted() -> None:
    email = "endpoint-test-doc-owner-15@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = upload_response.json()["id"]

        # Simulate extraction having already run and produced a real
        # recommendation, without needing a live Celery worker in this
        # HTTP-level test (extraction.py's own dispatch logic is tested
        # for real elsewhere -- test_extraction.py, live verification).
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key
            document.doc_metadata = {
                **document.doc_metadata,
                "chunking_recommendation": {
                    "strategy": "markdown_heading",
                    "scores": {},
                    "reasoning": "Recommended 'markdown_heading' (score 0.80): test fixture.",
                },
            }
            await session.commit()

        response = client.patch(
            _docs_url(org_id, workspace_id, kb_id, f"/{document_id}/chunking-strategy"),
            json={"strategy": "markdown_heading"},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["strategy"] == "markdown_heading"
        assert body["source"] == "accepted"
        assert body["reasoning"] == "Recommended 'markdown_heading' (score 0.80): test fixture."
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_override_chunking_strategy_different_from_recommendation() -> None:
    email = "endpoint-test-doc-owner-16@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = upload_response.json()["id"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key
            document.doc_metadata = {
                **document.doc_metadata,
                "chunking_recommendation": {
                    "strategy": "fixed_size",
                    "scores": {},
                    "reasoning": "Recommended 'fixed_size' (score 0.20): test fixture.",
                },
            }
            await session.commit()

        response = client.patch(
            _docs_url(org_id, workspace_id, kb_id, f"/{document_id}/chunking-strategy"),
            json={"strategy": "recursive_hybrid"},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["strategy"] == "recursive_hybrid"
        assert body["source"] == "override"
        assert "overriding the recommended 'fixed_size'" in body["reasoning"]
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_override_chunking_strategy_rejects_unknown_strategy_name() -> None:
    email = "endpoint-test-doc-owner-17@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", b"content", "text/plain")},
            headers=headers,
        )
        document_id = upload_response.json()["id"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key

        response = client.patch(
            _docs_url(org_id, workspace_id, kb_id, f"/{document_id}/chunking-strategy"),
            json={"strategy": "not_a_real_strategy"},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_override_chunking_strategy_for_nonexistent_document_returns_404() -> None:
    email = "endpoint-test-doc-owner-18@example.com"
    org_id, workspace_id, kb_id, headers = _new_org_with_kb(email)
    try:
        response = client.patch(
            _docs_url(org_id, workspace_id, kb_id, f"/{uuid.uuid4()}/chunking-strategy"),
            json={"strategy": "fixed_size"},
            headers=headers,
        )
        assert response.status_code == 404
    finally:
        await _cleanup_org(org_id)
        await _cleanup_user(email)


@pytest.mark.anyio
async def test_end_user_role_cannot_override_chunking_strategy() -> None:
    owner_email = "endpoint-test-doc-owner-19@example.com"
    org_id, workspace_id, kb_id, owner_headers = _new_org_with_kb(owner_email)
    storage_key = None
    try:
        upload_response = client.post(
            _docs_url(org_id, workspace_id, kb_id),
            files={"file": ("notes.txt", b"content", "text/plain")},
            headers=owner_headers,
        )
        document_id = upload_response.json()["id"]

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            document = await session.get(Document, uuid.UUID(document_id))
            assert document is not None
            storage_key = document.storage_key

        member_token = signup_and_login(
            client,
            email="endpoint-test-doc-chunk-member@example.com",
            password="correct horse battery staple",
            full_name="Chunking Override Member",
        )
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.email == "endpoint-test-doc-chunk-member@example.com")
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
            _docs_url(org_id, workspace_id, kb_id, f"/{document_id}/chunking-strategy"),
            json={"strategy": "fixed_size"},
            headers=auth_headers(member_token),
        )
        assert response.status_code == 403
    finally:
        if storage_key is not None:
            await _cleanup_storage(storage_key)
        await _cleanup_org(org_id)
        await _cleanup_user(owner_email)
        await _cleanup_user("endpoint-test-doc-chunk-member@example.com")
