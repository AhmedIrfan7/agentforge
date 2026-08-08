"""First model in the ingestion/RAG pipeline (roadmap step 082, Milestone
3) — sits under Workspace in the product hierarchy (AGENTS.md SECTION 3:
org -> workspace -> knowledge base -> assistant -> ...), one level
deeper than Workspace itself. Documents (step 083) belong to exactly one
KnowledgeBase the same way a KnowledgeBase belongs to exactly one
Workspace.

Deliberately minimal for now: no embedding-model/chunking-config fields
yet. Those are real per-knowledge-base decisions in a working RAG system
(chunks within one KB need a shared, comparable embedding space), but
speculating about their shape before the embedding-provider abstraction
(step 106) or chunking strategies (steps 098-102) exist would be
designing against a guess, not a requirement — AGENTS.md SECTION 14's
own operating rule. Those fields land with the migration that actually
needs them.
"""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class KnowledgeBase(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        # Slug unique within a workspace, not tenant-wide -- two
        # different workspaces in the same org can each reasonably want
        # a knowledge base named "docs".
        UniqueConstraint("workspace_id", "slug", name="uq_knowledge_bases_workspace_id_slug"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
