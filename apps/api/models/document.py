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

extracted_text (step 090): plain text produced by extraction.py's
dispatch_extraction task, nullable -- null until extraction actually
runs (or forever, for a status that never resolves past
"extraction_unsupported"). Postgres TEXT, not object storage: chunking
(steps 098+) will read this repeatedly and cheaply from the same query
that already loads the Document row, and TEXT/TOAST handles even a
large document's extracted text fine without a second storage round
trip for every read.

content_hash (step 096): SHA-256 of the raw uploaded bytes, indexed but
not unique -- duplicates are expected to exist and aren't rejected or
even flagged here, only made cheaply findable. Step 117 ("duplicate-
document detection within a knowledge base") owns deciding what to
actually DO with a duplicate; this step only computes and stores the
signal it needs, the same "build the primitive now, the feature that
uses it later" split already used for extracted_text itself (090)
versus chunking (098+). Nullable for the same reason extracted_text is
-- populated once quality.py's checks actually run, during extraction.

chunking_strategy/chunking_strategy_source/chunking_strategy_reasoning
(step 104): promoted out of doc_metadata["chunking_decision"] (step
103) into real columns -- unlike doc_metadata['chunking_recommendation']
(step 097), which stays JSONB because it's genuinely multi-field
diagnostic data (a score per candidate strategy), the final DECISION is
a single strategy name a later step (105+) needs to read cheaply and
reliably, not dig out of a JSONB blob. chunking_strategy_source is
"recommended" (extraction.py set it automatically, nobody's reviewed
it), "accepted" (a caller explicitly confirmed the recommendation), or
"override" (a caller explicitly chose differently) -- three states, not
two, because "nobody has looked at this yet" is meaningfully different
from "a human confirmed the algorithm's guess," e.g. for an eventual
admin review queue. extraction.py sets all three to a real default
(source="recommended") the moment a chunking_recommendation exists;
routers/document.py's override endpoint (step 103) updates them to
"accepted"/"override" on an explicit call. All nullable -- extraction
that never completes (extraction_unsupported/extraction_failed) never
gets a recommendation to base a default on either.
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
    extracted_text: Mapped[str | None] = mapped_column(nullable=True, default=None)
    content_hash: Mapped[str | None] = mapped_column(nullable=True, default=None, index=True)
    chunking_strategy: Mapped[str | None] = mapped_column(nullable=True, default=None)
    chunking_strategy_source: Mapped[str | None] = mapped_column(nullable=True, default=None)
    chunking_strategy_reasoning: Mapped[str | None] = mapped_column(nullable=True, default=None)
