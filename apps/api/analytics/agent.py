"""AnalyticsAgent skeleton (roadmap step 242).

AGENTS.md's own "ANALYTICS AGENT" section names 8 real responsibilities:
conversation metrics, knowledge metrics, agent performance, retrieval
quality, usage trends, failure patterns, latency, business insights.
This step is explicitly a skeleton, not all 8 built out -- the roadmap's
own later steps are each one category's real dashboard/endpoint (243
conversation-analytics, 244 knowledge-health, 245 agent-performance, 246
usage-tracking, 248 system-health). Building every category's full
query logic now, before any of those steps exists to consume or verify
it, would be exactly the "speculate about a shape a real caller hasn't
asked for yet" this codebase's own established discipline avoids
everywhere else (KnowledgeBase/Assistant/Message model docstrings all
make the identical argument).

conversation_metrics() (243) and knowledge_metrics() (244) are real,
working exceptions -- proving the skeleton is genuinely callable end to
end (real DB queries, real tests) rather than a class of empty names,
each filled in exactly when its own dedicated roadmap step arrived, not
speculatively ahead of it. Every other method still raises
NotImplementedError with a docstring naming its real future roadmap
step where one is already scheduled (through 250), or saying plainly
that none exists yet where AGENTS.md names the responsibility but no
roadmap step has claimed it -- an honest, discoverable interface for
those later steps to fill in, not a guessed one.

Not a TenantScopedRepository subclass (this computes aggregates across
several models, not CRUD on one) and not an Agent[InputT, OutputT]
subclass (agents/base.py's own docstring already established that
domain-specific, non-graph agents like DocumentAnalysisAgent aren't
forced onto that interface either) -- collaborators (session, tenant_id)
are passed per call, not held on the instance, matching
agents/retriever.py:RetrieverAgent's own "request-scoped collaborators
can't live on a module-level singleton" reasoning.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.conversation import Conversation
from models.document import Document
from models.message import Message

_RECENT_WINDOW = timedelta(days=7)

# A document's own chunking_recommendation.scores[chosen_strategy] is a
# real value in [0, 1] (agents/chunking_recommendation.py) -- not a
# fabricated confidence metric, but there's no established convention
# yet for what counts as "low." 0.5 (the scale's own midpoint) is a
# first, honest, easily-revisited heuristic, not a tuned threshold.
_LOW_CONFIDENCE_THRESHOLD = 0.5


@dataclass
class ConversationMetrics:
    total_conversations: int
    total_messages: int
    average_messages_per_conversation: float
    conversations_last_7_days: int


@dataclass
class KnowledgeMetrics:
    total_documents: int
    duplicate_document_count: int
    low_confidence_document_count: int
    unused_document_count: int


class AnalyticsAgent:
    name = "analytics"

    async def conversation_metrics(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> ConversationMetrics:
        total_conversations = (
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.tenant_id == tenant_id)
            )
            or 0
        )
        total_messages = (
            await session.scalar(
                select(func.count()).select_from(Message).where(Message.tenant_id == tenant_id)
            )
            or 0
        )
        since = datetime.now(UTC) - _RECENT_WINDOW
        conversations_last_7_days = (
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.tenant_id == tenant_id, Conversation.created_at >= since)
            )
            or 0
        )
        average = (total_messages / total_conversations) if total_conversations else 0.0
        return ConversationMetrics(
            total_conversations=total_conversations,
            total_messages=total_messages,
            average_messages_per_conversation=average,
            conversations_last_7_days=conversations_last_7_days,
        )

    async def knowledge_metrics(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> KnowledgeMetrics:
        """Real, not a stub -- reuses three signals this codebase already
        computes for real, unrelated reasons, rather than inventing new
        tracking data:
        - duplicates: extraction.py already writes doc_metadata
          ['duplicate_document_ids'] per document (step 117's own real
          content_hash-based detection) -- a document counts as a
          duplicate here iff that list is non-empty.
        - low-confidence: doc_metadata['chunking_recommendation']
          ['scores'][chunking_strategy] is the real score (step 097)
          the CHOSEN strategy actually got, not a fabricated number.
        - unused: a document that has never appeared in any real
          Message.citations (step 187) across this tenant -- the only
          honest signal available, since agents/tracing.py's own
          retrieval events are log-only, never persisted to a queryable
          table (its own module docstring already explains why nothing
          here tries to query them).
        """
        documents = (
            (await session.execute(select(Document).where(Document.tenant_id == tenant_id)))
            .scalars()
            .all()
        )
        total_documents = len(documents)

        duplicate_document_count = sum(
            1 for d in documents if d.doc_metadata.get("duplicate_document_ids")
        )

        low_confidence_document_count = 0
        for d in documents:
            if d.chunking_strategy is None:
                continue
            recommendation = d.doc_metadata.get("chunking_recommendation")
            scores = recommendation.get("scores") if isinstance(recommendation, dict) else None
            score = scores.get(d.chunking_strategy) if isinstance(scores, dict) else None
            if isinstance(score, int | float) and score < _LOW_CONFIDENCE_THRESHOLD:
                low_confidence_document_count += 1

        cited_document_ids: set[uuid.UUID] = set()
        if documents:
            # Same "app-layer filter on top of, not instead of, RLS"
            # discipline repositories/base.py's own docstring already
            # states -- the explicit tenant_id predicate isn't strictly
            # needed under RLS, but stays here for the same reason.
            result = await session.execute(
                text(
                    "SELECT DISTINCT (citation->>'document_id')::uuid AS document_id "
                    "FROM messages, jsonb_array_elements(citations) AS citation "
                    "WHERE tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            )
            cited_document_ids = {row.document_id for row in result.all()}

        unused_document_count = sum(1 for d in documents if d.id not in cited_document_ids)

        return KnowledgeMetrics(
            total_documents=total_documents,
            duplicate_document_count=duplicate_document_count,
            low_confidence_document_count=low_confidence_document_count,
            unused_document_count=unused_document_count,
        )

    async def agent_performance_metrics(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> NoReturn:
        """Per-agent latency/success, aggregated from the real per-
        execution events agents/tracing.py already logs -- roadmap step
        245 ("agent-performance dashboard")."""
        raise NotImplementedError("Agent-performance metrics land with roadmap step 245.")

    async def usage_metrics(self, session: AsyncSession, tenant_id: uuid.UUID) -> NoReturn:
        """Messages/voice-minutes/uploads/storage per org -- roadmap
        step 246 ("usage-tracking"). Deliberately NOT folded into
        conversation_metrics() above: 246 names these as their own
        distinct metric category, separate from conversation counts."""
        raise NotImplementedError("Usage metrics land with roadmap step 246.")

    async def retrieval_quality_metrics(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> NoReturn:
        """AGENTS.md's own ANALYTICS AGENT responsibility. eval/
        regression.py already covers a DIFFERENT concern (offline
        retrieval-quality regression testing against a fixture set, not
        live per-tenant analytics) -- no dedicated roadmap step names
        this specifically through 250; real, undated future work."""
        raise NotImplementedError("Retrieval-quality analytics has no dedicated roadmap step yet.")

    async def failure_pattern_metrics(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> NoReturn:
        """AGENTS.md's own ANALYTICS AGENT responsibility -- no
        dedicated roadmap step through 250; real, undated future work."""
        raise NotImplementedError("Failure-pattern analytics has no dedicated roadmap step yet.")

    async def latency_metrics(self, session: AsyncSession, tenant_id: uuid.UUID) -> NoReturn:
        """agents/tracing.py already logs real per-execution latency
        events -- aggregating them here is real, undated future work;
        no roadmap step through 250 names it specifically (245's own
        "agent-performance dashboard" is the closer real fit, but
        AGENTS.md lists them as separate responsibilities, so this
        stays its own method rather than being silently folded in)."""
        raise NotImplementedError("Latency analytics has no dedicated roadmap step yet.")

    async def business_insight_metrics(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> NoReturn:
        """AGENTS.md's own ANALYTICS AGENT responsibility -- no
        dedicated roadmap step through 250; real, undated future work."""
        raise NotImplementedError("Business-insight analytics has no dedicated roadmap step yet.")
