"""Tests for analytics/agent.py (roadmap step 242). Domain-level, not
endpoint-level -- AnalyticsAgent has no router yet (step 243's own
job), so this exercises it directly against a real DB session, same
"build fixtures directly via models, real Postgres, real tenant
context" pattern test_memory_repository.py already established for
non-endpoint domain tests.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from analytics.agent import AnalyticsAgent
from db import get_session, set_tenant_context
from models.assistant import Assistant
from models.conversation import Conversation
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.message import Message
from models.organization import Organization
from models.workspace import Workspace

agent = AnalyticsAgent()


async def _new_org(slug: str) -> uuid.UUID:
    async with get_session() as session:
        org = Organization(name="Analytics Agent Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await session.commit()
        return org.id


async def _new_assistant(tenant_id: uuid.UUID, slug: str) -> uuid.UUID:
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        workspace = Workspace(tenant_id=tenant_id, name="Analytics WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()
        knowledge_base = KnowledgeBase(
            tenant_id=tenant_id, workspace_id=workspace.id, name="Analytics KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()
        assistant = Assistant(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base.id,
            name="Analytics Bot",
            slug="bot",
        )
        session.add(assistant)
        await session.flush()
        await session.commit()
        return assistant.id


async def _new_conversation_with_messages(
    tenant_id: uuid.UUID,
    assistant_id: uuid.UUID,
    *,
    message_count: int,
    created_at: datetime | None = None,
) -> None:
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        conversation = Conversation(tenant_id=tenant_id, assistant_id=assistant_id)
        session.add(conversation)
        await session.flush()
        for i in range(message_count):
            session.add(
                Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"message {i}",
                )
            )
        await session.commit()
        if created_at is not None:
            # Backdate directly -- created_at has a server_default, no
            # constructor kwarg can set it, and the "last 7 days"
            # window genuinely needs an OLD conversation to prove it
            # excludes anything, not just that it includes recent ones.
            # set_tenant_context only lasts one transaction (SET LOCAL)
            # -- the commit() above already ended the one it was set
            # for, so RLS would silently match zero rows without
            # calling it again here.
            await set_tenant_context(session, tenant_id)
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation.id)
                .values(created_at=created_at)
            )
            await session.commit()


async def _new_knowledge_base(tenant_id: uuid.UUID, slug: str) -> uuid.UUID:
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        workspace = Workspace(tenant_id=tenant_id, name="Analytics WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()
        knowledge_base = KnowledgeBase(
            tenant_id=tenant_id, workspace_id=workspace.id, name="Analytics KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()
        await session.commit()
        return knowledge_base.id


async def _new_document(
    tenant_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    *,
    slug: str,
    doc_metadata: dict[str, object] | None = None,
    chunking_strategy: str | None = None,
) -> uuid.UUID:
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        document = Document(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            title=f"Doc {slug}",
            status="embedded",
            storage_key=f"analytics-test/{slug}",
            content_type="text/plain",
            size_bytes=10,
            doc_metadata=doc_metadata or {},
            chunking_strategy=chunking_strategy,
        )
        session.add(document)
        await session.flush()
        await session.commit()
        return document.id


async def _new_message_citing(
    tenant_id: uuid.UUID, assistant_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        conversation = Conversation(tenant_id=tenant_id, assistant_id=assistant_id)
        session.add(conversation)
        await session.flush()
        session.add(
            Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                role="assistant",
                content="Here's what I found.",
                citations=[
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "document_id": str(document_id),
                        "document_title": "cited doc",
                        "text": "excerpt",
                    }
                ],
            )
        )
        await session.commit()


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        for model in (Message, Conversation, Document, Assistant, KnowledgeBase, Workspace):
            result = await session.execute(select(model).where(model.tenant_id == org_id))
            for row in result.scalars().all():
                await session.delete(row)
            await session.flush()
        org = await session.get(Organization, org_id)
        if org is not None:
            await session.delete(org)
        await session.commit()


@pytest.mark.anyio
async def test_conversation_metrics_counts_real_conversations_and_messages() -> None:
    org_id = await _new_org("analytics-metrics")
    try:
        assistant_id = await _new_assistant(org_id, "analytics-metrics")
        await _new_conversation_with_messages(org_id, assistant_id, message_count=4)
        await _new_conversation_with_messages(org_id, assistant_id, message_count=2)

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            metrics = await agent.conversation_metrics(session, org_id)

        assert metrics.total_conversations == 2
        assert metrics.total_messages == 6
        assert metrics.average_messages_per_conversation == 3.0
        assert metrics.conversations_last_7_days == 2
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_conversation_metrics_excludes_old_conversations_from_the_7_day_window() -> None:
    org_id = await _new_org("analytics-oldwindow")
    try:
        assistant_id = await _new_assistant(org_id, "analytics-oldwindow")
        old_date = datetime.now(UTC) - timedelta(days=30)
        await _new_conversation_with_messages(
            org_id, assistant_id, message_count=1, created_at=old_date
        )
        await _new_conversation_with_messages(org_id, assistant_id, message_count=1)

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            metrics = await agent.conversation_metrics(session, org_id)

        assert metrics.total_conversations == 2
        assert metrics.conversations_last_7_days == 1
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_conversation_metrics_on_an_empty_org_is_all_zeroes_not_a_division_error() -> None:
    org_id = await _new_org("analytics-empty")
    try:
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            metrics = await agent.conversation_metrics(session, org_id)

        assert metrics.total_conversations == 0
        assert metrics.total_messages == 0
        assert metrics.average_messages_per_conversation == 0.0
        assert metrics.conversations_last_7_days == 0
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_conversation_metrics_is_scoped_to_its_own_tenant() -> None:
    org_a = await _new_org("analytics-tenant-a")
    org_b = await _new_org("analytics-tenant-b")
    try:
        assistant_a = await _new_assistant(org_a, "analytics-tenant-a")
        assistant_b = await _new_assistant(org_b, "analytics-tenant-b")
        await _new_conversation_with_messages(org_a, assistant_a, message_count=5)
        await _new_conversation_with_messages(org_b, assistant_b, message_count=1)

        async with get_session() as session:
            await set_tenant_context(session, org_a)
            metrics_a = await agent.conversation_metrics(session, org_a)

        assert metrics_a.total_conversations == 1
        assert metrics_a.total_messages == 5
    finally:
        await _cleanup_org(org_a)
        await _cleanup_org(org_b)


@pytest.mark.anyio
async def test_knowledge_metrics_counts_documents_flagged_as_duplicates() -> None:
    org_id = await _new_org("analytics-kb-dup")
    try:
        kb_id = await _new_knowledge_base(org_id, "analytics-kb-dup")
        original_id = await _new_document(org_id, kb_id, slug="original")
        await _new_document(
            org_id,
            kb_id,
            slug="dup",
            doc_metadata={"duplicate_document_ids": [str(original_id)]},
        )
        await _new_document(
            org_id, kb_id, slug="unique", doc_metadata={"duplicate_document_ids": []}
        )

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            metrics = await agent.knowledge_metrics(session, org_id)

        assert metrics.total_documents == 3
        assert metrics.duplicate_document_count == 1
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_knowledge_metrics_counts_low_confidence_chunking_decisions() -> None:
    org_id = await _new_org("analytics-kb-lowconf")
    try:
        kb_id = await _new_knowledge_base(org_id, "analytics-kb-lowconf")
        await _new_document(
            org_id,
            kb_id,
            slug="weak",
            chunking_strategy="fixed_size",
            doc_metadata={
                "chunking_recommendation": {"scores": {"fixed_size": 0.2, "markdown_heading": 0.8}}
            },
        )
        await _new_document(
            org_id,
            kb_id,
            slug="strong",
            chunking_strategy="markdown_heading",
            doc_metadata={
                "chunking_recommendation": {"scores": {"fixed_size": 0.2, "markdown_heading": 0.8}}
            },
        )
        # Never extracted -- no chunking_strategy at all yet. Must not
        # be miscounted as low-confidence just because it has no score.
        await _new_document(org_id, kb_id, slug="pending")

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            metrics = await agent.knowledge_metrics(session, org_id)

        assert metrics.total_documents == 3
        assert metrics.low_confidence_document_count == 1
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_knowledge_metrics_counts_documents_never_cited_in_a_message() -> None:
    org_id = await _new_org("analytics-kb-unused")
    try:
        kb_id = await _new_knowledge_base(org_id, "analytics-kb-unused-1")
        assistant_id = await _new_assistant(org_id, "analytics-kb-unused-2")
        cited_id = await _new_document(org_id, kb_id, slug="cited")
        await _new_document(org_id, kb_id, slug="never-cited")
        await _new_message_citing(org_id, assistant_id, cited_id)

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            metrics = await agent.knowledge_metrics(session, org_id)

        assert metrics.total_documents == 2
        assert metrics.unused_document_count == 1
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_knowledge_metrics_on_an_empty_org_is_all_zeroes() -> None:
    org_id = await _new_org("analytics-kb-empty")
    try:
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            metrics = await agent.knowledge_metrics(session, org_id)

        assert metrics.total_documents == 0
        assert metrics.duplicate_document_count == 0
        assert metrics.low_confidence_document_count == 0
        assert metrics.unused_document_count == 0
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_knowledge_metrics_is_scoped_to_its_own_tenant() -> None:
    org_a = await _new_org("analytics-kb-tenant-a")
    org_b = await _new_org("analytics-kb-tenant-b")
    try:
        kb_a = await _new_knowledge_base(org_a, "analytics-kb-tenant-a")
        kb_b = await _new_knowledge_base(org_b, "analytics-kb-tenant-b")
        await _new_document(org_a, kb_a, slug="doc-a")
        await _new_document(org_b, kb_b, slug="doc-b1")
        await _new_document(org_b, kb_b, slug="doc-b2")

        async with get_session() as session:
            await set_tenant_context(session, org_a)
            metrics_a = await agent.knowledge_metrics(session, org_a)

        assert metrics_a.total_documents == 1
    finally:
        await _cleanup_org(org_a)
        await _cleanup_org(org_b)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "method_name",
    [
        "agent_performance_metrics",
        "usage_metrics",
        "retrieval_quality_metrics",
        "failure_pattern_metrics",
        "latency_metrics",
        "business_insight_metrics",
    ],
)
async def test_unbuilt_metric_categories_raise_not_implemented_not_silently_return_nothing(
    method_name: str,
) -> None:
    """Proves each stub is a deliberate, discoverable gap -- not an
    accidental missing return that would silently look like "zero
    activity" to a future caller."""
    org_id = await _new_org(f"analytics-stub-{method_name[:8]}")
    try:
        async with get_session() as session:
            await set_tenant_context(session, org_id)
            method = getattr(agent, method_name)
            with pytest.raises(NotImplementedError):
                await method(session, org_id)
    finally:
        await _cleanup_org(org_id)
