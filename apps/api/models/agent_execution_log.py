"""Persisted record of one traced agent run (roadmap step 245's own
real backend gap: agents/tracing.py (153) has logged agent_execution
events structurally since Milestone 4, but ONLY as structlog output --
never to a queryable table. A real "agent-performance dashboard"
(245's own literal wording) needs real HISTORY to aggregate, which
log lines alone can't give a caller; this table is that missing
primitive, the same "build the primitive now, the feature that needs
it lands with it" shape content_hash (096) already established for
duplicate detection (117).

Deliberately minimal -- agent_name/status/latency_ms only, matching
AgentExecutionTrace's own core fields (agents/tracing.py). No token
counts: those are a cost/usage concern (roadmap step 246's own
"usage-tracking" domain), not "performance" in the latency/success
sense this step's literal wording asks for, and AgentExecutionTrace's
own token fields are still honestly None for every real agent in this
codebase today (no agent calls an LLM yet) -- persisting a column that
would always be NULL right now is exactly the kind of premature field
this project's own discipline avoids.
"""

from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class AgentExecutionLog(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "agent_execution_logs"

    agent_name: Mapped[str] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(nullable=False)
    latency_ms: Mapped[float] = mapped_column(nullable=False)
