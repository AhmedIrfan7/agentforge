"""Second model in the ingestion/RAG pipeline (roadmap step 083, storage
columns added by step 084) — sits under KnowledgeBase (org -> workspace
-> knowledge base -> document).

status is a plain str, not a DB enum — same reasoning as
VerificationToken.purpose and Invitation's status: a new pipeline stage
(virus scan, extraction, chunking, embedding — steps 087+) is an
application-level addition as the pipeline gets built out, not a
migration. Starts at "pending" (uploaded, not yet processed); later
steps define and transition through whatever further values they need.

doc_metadata (not `metadata` — that name is reserved on every SQLAlchemy
declarative model, it's the class-level MetaData registry) holds
extracted title/author/dates/language once step 094's metadata-
extraction step populates it. Empty by default, not nullable — an empty
dict and "no metadata extracted yet" are the same thing, no reason to
also support NULL for it.

storage_key/content_type/size_bytes (step 084): storage_key is the
object's path in the bucket (storage/client.py), never returned by the
API — an internal implementation detail, not something a client needs
or should be able to guess/tamper with.
"""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Document(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "documents"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, default="pending")
    doc_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    storage_key: Mapped[str] = mapped_column(nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
