"""Analytics endpoints -- conversations (step 243), knowledge health
(244), agent performance (245), each the first real caller of its own
analytics/agent.py:AnalyticsAgent method. `_analytics_agent` is a
module-level singleton, same shape routers/retrieval.py's own
`_retriever_agent` already established: the agent itself is stateless
(no per-request collaborator held on the instance), only the
session/tenant_id passed into each call are request-scoped.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.agent import AnalyticsAgent
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from schemas.analytics import (
    AgentPerformanceEntryRead,
    AgentPerformanceMetricsRead,
    ConversationMetricsRead,
    KnowledgeMetricsRead,
)

router = APIRouter(prefix="/organizations/{organization_id}/analytics", tags=["analytics"])

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]

_analytics_agent = AnalyticsAgent()


@router.get(
    "/conversations",
    response_model=ConversationMetricsRead,
    dependencies=[Depends(require_permission("analytics:read"))],
)
async def get_conversation_metrics(
    session: TenantDb, tenant_id: TenantId
) -> ConversationMetricsRead:
    metrics = await _analytics_agent.conversation_metrics(session, tenant_id)
    return ConversationMetricsRead(
        total_conversations=metrics.total_conversations,
        total_messages=metrics.total_messages,
        average_messages_per_conversation=metrics.average_messages_per_conversation,
        conversations_last_7_days=metrics.conversations_last_7_days,
    )


@router.get(
    "/knowledge",
    response_model=KnowledgeMetricsRead,
    dependencies=[Depends(require_permission("analytics:read"))],
)
async def get_knowledge_metrics(session: TenantDb, tenant_id: TenantId) -> KnowledgeMetricsRead:
    metrics = await _analytics_agent.knowledge_metrics(session, tenant_id)
    return KnowledgeMetricsRead(
        total_documents=metrics.total_documents,
        duplicate_document_count=metrics.duplicate_document_count,
        low_confidence_document_count=metrics.low_confidence_document_count,
        unused_document_count=metrics.unused_document_count,
    )


@router.get(
    "/agent-performance",
    response_model=AgentPerformanceMetricsRead,
    dependencies=[Depends(require_permission("analytics:read"))],
)
async def get_agent_performance_metrics(
    session: TenantDb, tenant_id: TenantId
) -> AgentPerformanceMetricsRead:
    metrics = await _analytics_agent.agent_performance_metrics(session, tenant_id)
    return AgentPerformanceMetricsRead(
        per_agent=[
            AgentPerformanceEntryRead(
                agent_name=entry.agent_name,
                execution_count=entry.execution_count,
                success_rate=entry.success_rate,
                average_latency_ms=entry.average_latency_ms,
            )
            for entry in metrics.per_agent
        ]
    )
