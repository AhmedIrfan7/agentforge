"""Assistant model (roadmap step 159, Milestone 4) -- sits under
KnowledgeBase in the product hierarchy (AGENTS.md's own "ORGANIZATION
STRUCTURE" diagram: Organization -> Workspace(s) -> Knowledge Base(s)
-> AI Assistant(s) -> ...), one level deeper than KnowledgeBase itself
-- the same "one parent FK, mirroring the hierarchy" shape
KnowledgeBase (082) already established under Workspace.

Genuinely model-only, same precedent Document (083) and Chunk (105)
already set: step 160 ("Add Assistant CRUD endpoints") is its own,
separate roadmap step -- unlike KnowledgeBase (082), which bundled a
minimal CRUD into its own model step because no later dedicated CRUD
step existed for it. No repository yet either, same reasoning Chunk's
own step-105 docstring gave.

Deliberately minimal beyond name/slug/description -- same "don't
speculate about fields a real step hasn't asked for yet" discipline
KnowledgeBase's own docstring already applied. AGENTS.md's own "AI
ASSISTANTS" section lists many more per-assistant concerns
(instructions, knowledge access, voice configuration, memory settings,
security policies, deployment settings, analytics, future tool
integrations), but none of those have a real, already-built shape to
store yet -- except `agent_configuration`, step 158's own
`agents/configuration.py:AgentConfiguration`, built specifically so
this step would have a real payload. Stored as JSONB
(`Mapped[dict[str, object]]`), matching `models/document.py`'s own
`doc_metadata` JSONB column -- the same "validated structure at the
application layer, flexible storage at the DB layer" split. This
model stays SQLAlchemy-only (no Pydantic import), matching every other
`models/*.py` file -- validating a write against `AgentConfiguration`
is the future CRUD endpoint's job (step 160), not this table's.

As of step 192, `is_public` lands: defaults `False` -- anonymous
access (`routers/public_conversation.py`) is opt-in per assistant, not
automatic just because a caller learned its (non-guessable, but not
secret) UUID. A real, explicit authorization control, not just relying
on `UUIDPrimaryKeyMixin`'s own "hard to guess" property as the only
thing standing between the public internet and an org's assistant --
same "non-guessable ID is defense in depth, not the whole control"
reasoning invitation tokens already established (hashed + a real
expiry/accepted/revoked lifecycle, not just an unguessable value).

As of step 238 (the assistant-builder UI), `instructions` (nullable
system-prompt text) lands and a real `PATCH .../assistants/{id}`
endpoint finally exists (`assistant:update`, migration `331109d18ff0`)
-- the "no update endpoint yet" limitation this docstring used to note
for `is_public` no longer applies to any field on this model; that
endpoint updates name/description/instructions/agent_configuration/
is_public uniformly, the same `model_fields_set`-driven PATCH pattern
every other update endpoint in this codebase already uses.
"""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class Assistant(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "assistants"
    __table_args__ = (
        # Slug unique within a knowledge base, not tenant-wide -- same
        # "two different parents can each reasonably reuse a name"
        # reasoning KnowledgeBase's own uq_knowledge_bases_workspace_id_slug
        # already established one level up.
        UniqueConstraint("knowledge_base_id", "slug", name="uq_assistants_knowledge_base_id_slug"),
    )

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    # System-prompt instructions (roadmap step 238, AGENTS.md's own "AI
    # ASSISTANTS" list) -- nullable, unlike agent_configuration (a real
    # default already existed from step 158): an assistant with no
    # instructions yet is a normal, honest state, not one needing a
    # default value.
    instructions: Mapped[str | None] = mapped_column(nullable=True)
    agent_configuration: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    is_public: Mapped[bool] = mapped_column(nullable=False, default=False)
