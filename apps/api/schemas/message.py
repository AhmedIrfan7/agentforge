import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from message_rendering import render_markdown


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class CitationRead(BaseModel):
    """Roadmap step 187 -- mirrors citations.py:Citation's own field
    shape exactly (a genuine Pydantic twin, not a reinvention), so
    routers/conversation.py can build real Citation objects and store
    them as JSON-safe dicts (`.model_dump(mode="json")`) on
    Message.citations -- see that column's own docstring for why a
    plain Pydantic model, not the dataclass itself, is what actually
    gets serialized into JSONB (real, checked UUID-in-JSON handling,
    not assumed)."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    knowledge_base_name: str
    section: str | None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: list[CitationRead]
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_html(self) -> str:
        """Roadmap step 185 -- sanitized markdown->HTML, computed fresh
        on every serialization (see message_rendering.py's own
        docstring for why this isn't stored/cached)."""
        return render_markdown(self.content)


class ConversationSearchRequest(BaseModel):
    """Shared request shape for conversation search's two mechanisms
    (roadmap step 183) -- same "identical fields, defined once" pattern
    schemas/retrieval.py:SearchRequest already established for dense/
    keyword/hybrid chunk search."""

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)


class MessageSearchResultRead(BaseModel):
    """Deliberately minimal, same "plumbing-proving, not the polished
    product-facing shape" reasoning schemas/retrieval.py:SearchResultRead
    already established -- returns the matching MESSAGE, not an
    aggregated parent Conversation, same "search returns the matching
    unit" convention agents/retriever.py's own chunk-level results
    already set."""

    message_id: uuid.UUID
    conversation_id: uuid.UUID
    content: str
    score: float
