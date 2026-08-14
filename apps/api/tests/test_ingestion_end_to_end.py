"""End-to-end ingestion pipeline test (roadmap step 113): a real PDF,
uploaded through the real HTTP endpoint, chunked and embedded through
the real Celery task chain -- upload -> extraction (real PDF parsing,
document analysis, quality assessment, chunking recommendation) ->
chunk generation -> batched embedding generation -> pipeline-status
endpoint. Same "one continuous chain with real data, not fresh isolated
fixtures per assertion" reasoning test_full_auth_flow.py (step 080)
already established for this project's other milestone-closing
integration test -- the value here is proving the whole realistic
document journey works TOGETHER, the kind of integration gap
per-stage test files (test_extraction.py, test_embeddings_pipeline.py,
etc.) can't catch even if each passes individually.

No live worker process is used -- dispatch_extraction.apply() and
dispatch_embedding_generation.apply() run the REAL Celery task bodies
synchronously (Task.apply(), same "no broker/worker needed" reasoning
test_celery_app.py's ping test and test_pipeline_retry.py already
established), with dispatch_embedding_generation.delay monkeypatched to
immediately call .apply() in-process instead of publishing to Redis --
this exercises the real dispatch chain extraction.py:dispatch_extraction
triggers on success (step 108), not just the inner coroutines, without
a dangling unconsumed broker message.

Deliberately NOT an async test, unlike most of this project's DB-facing
tests: dispatch_extraction/dispatch_embedding_generation each call
asyncio.run() internally (they're written to run inside a synchronous
Celery worker, not an already-running event loop), so calling .apply()
from inside a pytest-anyio async test raises "asyncio.run() cannot be
called from a running event loop" -- caught live while writing this
test, not assumed. Each async DB-verification step below runs through
its own short-lived asyncio.run() call instead, sequenced around the
synchronous .apply() calls rather than sharing one long-lived loop with
them.

No real OPENAI_API_KEY exists in this environment (same documented gap
as steps 107/108/111/112) -- the roadmap's own literal ask is "fixture
PDF -> chunks+embeddings", which means reaching a genuine "embedded"
terminal state with real Chunk rows, not stopping at "embedding_failed".
embeddings_pipeline._embedding_provider is swapped for a fake (same
established pattern test_embeddings_pipeline.py already uses), rather
than silently skipping the one assertion the step's own name asks for.
"""

import asyncio
import io
import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate
from sqlalchemy import select

import embeddings_pipeline
import extraction
from db import get_session, set_tenant_context
from main import app
from models.audit_log import AuditLog
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.membership import Membership
from models.organization import Organization
from models.session import Session
from models.user import User
from models.workspace import Workspace
from storage import _client_context
from tests.helpers import auth_headers, signup_and_login

client = TestClient(app)

_STYLES = getSampleStyleSheet()


def _build_fixture_pdf() -> bytes:
    buf = io.BytesIO()
    SimpleDocTemplate(buf).build(
        [
            Paragraph("Quarterly Report", _STYLES["Title"]),
            Paragraph("Revenue Summary", _STYLES["Heading2"]),
            Paragraph(
                "Revenue grew across every region this quarter, driven by strong "
                "demand in enterprise accounts. Customer retention stayed high, "
                "with churn falling below three percent for the second period "
                "running. " * 3,
                _STYLES["Normal"],
            ),
            Paragraph("Product Notes", _STYLES["Heading2"]),
            Paragraph(
                "Support tickets decreased after the new onboarding flow "
                "launched. The redesigned setup wizard and clearer "
                "documentation both get credit for the improvement. " * 3,
                _STYLES["Normal"],
            ),
        ]
    )
    return buf.getvalue()


@dataclass
class _FakeEmbeddingProvider:
    name: str = "fake"
    dimensions: int = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] * self.dimensions for text in texts]


async def _get_document(org_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        return await session.get(Document, document_id)


async def _get_chunks(org_id: uuid.UUID, document_id: uuid.UUID) -> list[Chunk]:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.index)
        )
        return list(result.scalars().all())


async def _cleanup(org_id: uuid.UUID, email: str, storage_key: str | None) -> None:
    if storage_key is not None:
        async with _client_context() as s3:
            await s3.delete_object(Bucket="agentforge-dev", Key=storage_key)
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Chunk, Document, KnowledgeBase, Workspace, AuditLog, Membership):
            result = await session.execute(select(model).where(model.tenant_id == org_id))
            for row in result.scalars().all():
                await session.delete(row)
            await session.flush()
        org = await session.get(Organization, org_id)
        if org is not None:
            await session.delete(org)
        await session.commit()

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


def test_fixture_pdf_flows_end_to_end_to_chunks_and_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(embeddings_pipeline, "_embedding_provider", _FakeEmbeddingProvider())
    monkeypatch.setattr(
        embeddings_pipeline.dispatch_embedding_generation,
        "delay",
        lambda document_id, tenant_id: embeddings_pipeline.dispatch_embedding_generation.apply(
            args=(document_id, tenant_id)
        ),
    )

    email = "endpoint-test-e2e-ingestion@example.com"
    token = signup_and_login(
        client, email=email, password="correct horse battery staple", full_name="E2E Ingestion"
    )
    headers = auth_headers(token)
    org_id = uuid.uuid4()  # placeholder until the real org is created below
    storage_key = None
    try:
        # 1. Real org/workspace/knowledge base, through real endpoints.
        org_response = client.post(
            "/organizations",
            json={"name": "E2E Ingestion Org", "slug": "e2e-ingestion-org"},
            headers=headers,
        )
        assert org_response.status_code == 201
        org_id = uuid.UUID(org_response.json()["id"])

        ws_response = client.post(
            f"/organizations/{org_id}/workspaces",
            json={"name": "E2E Ingestion WS", "slug": "e2e-ingestion-ws"},
            headers=headers,
        )
        workspace_id = uuid.UUID(ws_response.json()["id"])

        kb_response = client.post(
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
            json={"name": "E2E Ingestion KB", "slug": "e2e-ingestion-kb"},
            headers=headers,
        )
        kb_id = uuid.UUID(kb_response.json()["id"])

        docs_url = (
            f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases/{kb_id}/documents"
        )

        # 2. Upload a real PDF through the real endpoint.
        pdf_bytes = _build_fixture_pdf()
        upload_response = client.post(
            docs_url,
            files={"file": ("quarterly-report.pdf", pdf_bytes, "application/pdf")},
            headers=headers,
        )
        assert upload_response.status_code == 201
        document_id = upload_response.json()["id"]

        document = asyncio.run(_get_document(org_id, uuid.UUID(document_id)))
        assert document is not None
        storage_key = document.storage_key

        # 3. Run the real dispatch chain: extraction -> (on success)
        # embedding generation, exactly as extraction.py:dispatch_
        # extraction triggers it in production, no live worker needed.
        extraction_result = extraction.dispatch_extraction.apply(args=(document_id, str(org_id)))
        assert extraction_result.successful()

        document = asyncio.run(_get_document(org_id, uuid.UUID(document_id)))
        assert document is not None
        assert document.status == "embedded"
        assert document.chunking_strategy is not None
        assert "# Quarterly Report" in (document.extracted_text or "")

        # 4. Real Chunk rows, with real (fake-provider) embeddings.
        chunks = asyncio.run(_get_chunks(org_id, uuid.UUID(document_id)))
        assert len(chunks) >= 1
        assert [c.index for c in chunks] == list(range(len(chunks)))
        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1536

        # 5. The pipeline-status endpoint (step 111) agrees with the
        # real DB state, tying this milestone's last few steps together.
        status_response = client.get(f"{docs_url}/{document_id}/pipeline-status", headers=headers)
        assert status_response.status_code == 200
        body = status_response.json()
        assert body["status"] == "embedded"
        assert body["chunk_count"] == len(chunks)
        assert body["embedded_chunk_count"] == len(chunks)
        assert {s["stage"]: s["status"] for s in body["stages"]} == {
            "extraction": "completed",
            "chunk_generation": "completed",
            "embedding_generation": "completed",
        }
    finally:
        asyncio.run(_cleanup(org_id, email, storage_key))
