"""Model-only test (roadmap step 083) -- no endpoint exists yet
(step 084, file upload, is what actually creates a Document; see
models/document.py's docstring for why). Same pattern as
test_workspace_model.py and test_organization_model.py: exercises the
ORM/RLS layer directly, since there's no router to go through.
"""

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace


@pytest.mark.anyio
async def test_create_and_read_document_within_tenant_context() -> None:
    # flush (not commit): RLS is still enforced per-statement, but
    # nothing persists once the session closes without committing — see
    # tests/test_tenant_isolation.py's module docstring.
    async with get_session() as session:
        org = Organization(name="Document Test Org", slug="document-test-org")
        session.add(org)
        await session.flush()

        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Engineering", slug="engineering")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Docs", slug="docs"
        )
        session.add(knowledge_base)
        await session.flush()

        document = Document(
            tenant_id=org.id,
            knowledge_base_id=knowledge_base.id,
            title="Employee Handbook.pdf",
            storage_key="document-test-org/docs/handbook.pdf",
            content_type="application/pdf",
            size_bytes=1024,
        )
        session.add(document)
        await session.flush()

        result = await session.execute(
            select(Document).where(Document.title == "Employee Handbook.pdf")
        )
        fetched = result.scalar_one()
        assert fetched.tenant_id == org.id
        assert fetched.knowledge_base_id == knowledge_base.id
        # Defaults, not explicitly set above.
        assert fetched.status == "pending"
        assert fetched.doc_metadata == {}


@pytest.mark.anyio
async def test_doc_metadata_round_trips_arbitrary_json() -> None:
    async with get_session() as session:
        org = Organization(name="Metadata Test Org", slug="metadata-test-org")
        session.add(org)
        await session.flush()

        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Ops", slug="ops")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Policies", slug="policies"
        )
        session.add(knowledge_base)
        await session.flush()

        document = Document(
            tenant_id=org.id,
            knowledge_base_id=knowledge_base.id,
            title="Policy.docx",
            status="ready",
            doc_metadata={"title": "PTO Policy", "author": "HR", "language": "en"},
            storage_key="metadata-test-org/policies/policy.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=2048,
        )
        session.add(document)
        await session.flush()

        result = await session.execute(select(Document).where(Document.title == "Policy.docx"))
        fetched = result.scalar_one()
        assert fetched.status == "ready"
        assert fetched.doc_metadata == {"title": "PTO Policy", "author": "HR", "language": "en"}
