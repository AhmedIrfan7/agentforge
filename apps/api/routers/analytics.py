"""Conversation-analytics endpoint (roadmap step 243) -- the first real
caller of analytics/agent.py:AnalyticsAgent.conversation_metrics (242).
`_analytics_agent` is a module-level singleton, same shape routers/
retrieval.py's own `_retriever_agent` already established: the agent
itself is stateless (no per-request collaborator held on the
instance), only the session/tenant_id passed into each call are
request-scoped.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.agent import AnalyticsAgent
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from schemas.analytics import ConversationMetricsRead

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
