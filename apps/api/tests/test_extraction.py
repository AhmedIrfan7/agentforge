"""Tests for extraction.py (roadmap step 090) -- exercises
_run_extraction directly against real Postgres + real MinIO (same "no
mocks for infrastructure this project owns" reasoning as
test_document_endpoints.py), not through a real Celery worker: nothing
here needs to prove Celery's own broker/worker plumbing works (step 089
already did, both in test_celery_app.py and live verification) -- only
that this task's own logic (routing by extension, status transitions,
storing extracted text) is correct. The real .delay() round trip through
routers/document.py:upload_document is covered by live verification
instead, same split step 089 used.
"""

import uuid

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from extraction import HANDLERS, _DocumentNotFoundYet, _run_extraction
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace
from storage import _client_context, ensure_bucket_exists, upload_file


async def _new_org_workspace_kb(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Extraction Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Extraction WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Extraction KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()
        await session.commit()
        return org.id, knowledge_base.id


async def _create_document(
    tenant_id: uuid.UUID, knowledge_base_id: uuid.UUID, *, title: str, content: bytes
) -> tuple[uuid.UUID, str]:
    storage_key = f"{tenant_id}/{knowledge_base_id}/{uuid.uuid4()}/{title}"
    await ensure_bucket_exists()
    await upload_file(key=storage_key, content=content, content_type="text/plain")

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
            storage_key=storage_key,
            content_type="text/plain",
            size_bytes=len(content),
        )
        session.add(document)
        await session.commit()
        return document.id, storage_key


async def _cleanup(tenant_id: uuid.UUID, storage_key: str | None = None) -> None:
    if storage_key is not None:
        async with _client_context() as s3:
            await s3.delete_object(Bucket="agentforge-dev", Key=storage_key)
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        for model in (Document, KnowledgeBase, Workspace):
            result = await session.execute(select(model).where(model.tenant_id == tenant_id))
            for row in result.scalars().all():
                await session.delete(row)
            await session.flush()
        org = await session.get(Organization, tenant_id)
        if org is not None:
            await session.delete(org)
        await session.commit()


def test_plain_text_extensions_are_registered() -> None:
    assert set(HANDLERS.keys()) == {"csv", "txt", "json", "xml"}


def test_markdown_is_deliberately_not_registered_yet() -> None:
    # Real structure-aware markdown extraction is step 093's job, not a
    # plain-text passthrough -- this guards against someone "helpfully"
    # adding it here by analogy to the other text types.
    assert "md" not in HANDLERS


@pytest.mark.anyio
async def test_supported_type_extracts_and_marks_extracted() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb("extract-supported")
    storage_key = None
    try:
        content = b"line one\nline two\n"
        document_id, storage_key = await _create_document(
            tenant_id, kb_id, title="notes.txt", content=content
        )

        await _run_extraction(document_id, tenant_id)

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            document = await session.get(Document, document_id)
            assert document is not None
            assert document.status == "extracted"
            assert document.extracted_text == content.decode("utf-8")
    finally:
        await _cleanup(tenant_id, storage_key)


@pytest.mark.anyio
async def test_unsupported_type_marks_extraction_unsupported() -> None:
    tenant_id, kb_id = await _new_org_workspace_kb("extract-unsupported")
    storage_key = None
    try:
        content = b"%PDF-1.4\nnot a real pdf body"
        document_id, storage_key = await _create_document(
            tenant_id, kb_id, title="report.pdf", content=content
        )

        await _run_extraction(document_id, tenant_id)

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            document = await session.get(Document, document_id)
            assert document is not None
            assert document.status == "extraction_unsupported"
            assert document.extracted_text is None
    finally:
        await _cleanup(tenant_id, storage_key)


@pytest.mark.anyio
async def test_missing_document_raises_not_found_yet() -> None:
    tenant_id, _kb_id = await _new_org_workspace_kb("extract-missing")
    try:
        with pytest.raises(_DocumentNotFoundYet):
            await _run_extraction(uuid.uuid4(), tenant_id)
    finally:
        await _cleanup(tenant_id)
