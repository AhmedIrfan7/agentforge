"""DocumentVersion (roadmap step 115) -- a snapshot of a Document's own
fields taken right before a new file replaces its content, not a
parallel history of Chunk/embedding state. "Preserves history" means
being able to see what a document used to be (title/storage_key/
content_type/size_bytes/extracted_text/content_hash/chunking decision/
doc_metadata at that point in time), not re-running retrieval against
an old version's chunks -- Chunk rows belong to whatever content is
CURRENT (step 114's delete-then-replace already established that a
document has exactly one live set of chunks at a time), and building a
second, parallel chunk-versioning system isn't what this step's own
wording ("replace preserves history") asks for.

storage_key is snapshotted, not deleted or overwritten -- the OLD
object stays in MinIO/S3 under its own key, so a version's raw bytes
stay fetchable later even though `Document.storage_key` itself now
points at the new upload. Nothing here deletes old storage objects;
that's real, deliberate future work (a retention/cleanup policy) this
step doesn't need to solve.

version_number is 1-indexed and derived by counting existing
DocumentVersion rows for the document at snapshot time, not a counter
column on Document itself -- one less place the two tables could drift
out of sync, and the count is already a cheap indexed query
(document_id is indexed, same as every other FK in this pipeline).
"""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class DocumentVersion(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_id_version"
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    storage_key: Mapped[str] = mapped_column(nullable=False)
    content_type: Mapped[str] = mapped_column(nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    doc_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    extracted_text: Mapped[str | None] = mapped_column(nullable=True, default=None)
    content_hash: Mapped[str | None] = mapped_column(nullable=True, default=None)
    chunking_strategy: Mapped[str | None] = mapped_column(nullable=True, default=None)
    chunking_strategy_source: Mapped[str | None] = mapped_column(nullable=True, default=None)
    chunking_strategy_reasoning: Mapped[str | None] = mapped_column(nullable=True, default=None)
