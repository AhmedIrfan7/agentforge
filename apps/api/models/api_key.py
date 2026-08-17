"""A long-lived credential an organization generates for itself
(roadmap step 241, AGENTS.md's own "ORGANIZATION MANAGEMENT" list --
API keys alongside Members/Roles/Knowledge bases/Assistants -- and its
"API SECURITY" section, which names "API key validation" as a real
expected capability). Tenant-scoped, same reasoning every other
per-org resource already has.

Same hash-and-prefix shape auth/api_keys.py's own generator produces:
key_hash is what a real lookup matches against (never the raw key,
which only ever exists in memory and the one-time create response);
key_prefix is the raw key's own first several characters, stored in
plaintext purely so a list view can show "which key is this" (afk_
live_a1b2c3d4...) without ever re-displaying the full secret -- the
same UX real providers (GitHub PATs, Stripe) use.

Deliberately NO last_used_at or expires_at yet: this step builds real
generation/listing/revocation, but does not wire API-key
authentication into the rest of the API (that's real, separate,
future work AGENTS.md's own "PUBLIC API STRATEGY"/"THIRD-PARTY
INTEGRATIONS" sections describe with "eventually" language, not
something this step's literal wording asks for). A last_used_at column
nothing could ever set would be exactly the kind of dead field this
codebase's own discipline avoids (see KnowledgeBase's/Assistant's own
docstrings on the same principle) -- add it once a real authentication
path exists to populate it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class ApiKey(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(nullable=False)
    key_hash: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
