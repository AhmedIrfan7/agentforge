"""VectorStore (roadmap step 118) -- a structural Protocol, same
reasoning as embeddings/base.py:EmbeddingProvider and auth/oauth.py:
OAuthProvider: nothing here needs inheritance or shared state, and the
roadmap's own preamble ("Every provider-facing piece -- LLM, embeddings,
speech, vector store -- sits behind an abstraction interface... swapping
providers later must never require a rewrite") is what justifies this
existing as a real interface rather than routers/retrieval code calling
pgvector queries directly.

upsert() and search() are the two halves a genuine STORE needs -- not
just a searcher: a vector store implementation swapped in later
(Pinecone, Qdrant, a different pgvector schema, etc.) needs its own way
of representing "these chunks live here too," not only a way to query
whatever's already there. Both are tenant- and knowledge-base-scoped
explicitly, matching this project's consistent defense-in-depth
tenant-isolation discipline (repositories/base.py's own docstring: "the
app-layer half of the defense-in-depth ADR-0003 calls for") -- a vector
store implementation is exactly the kind of place a forgotten tenant
filter would leak data across tenants, so it's a required parameter on
every call, not an afterthought.

As of step 123, search() takes an optional SearchFilters -- deliberately
NOT a speculative generic filter DSL, but exactly the two fields that
are actually real and populated today: document_id (scope to one
document, a common real RAG need) and document_type (agents/
document_analysis.py's own classification, step 095, already stored in
Document.doc_metadata). Both live on Document, not Chunk -- filtering
means joining through Document, the same join every implementation of
this interface already needs for knowledge_base_id scoping. No
generic "filter by any doc_metadata key" mechanism: that would be
designing against a guess about what a caller might someday want,
rather than the two fields this codebase can actually already answer
queries about.

VectorRecord/VectorSearchResult intentionally don't carry start/end/
index -- those are pgvector-adapter-specific implementation details
(models/chunk.py's own columns), not something every possible vector
store backend would have a concept of. A search result needs enough to
be useful to a caller building an answer: which chunk, which document,
its text, and how well it matched.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VectorRecord:
    id: uuid.UUID
    document_id: uuid.UUID
    text: str
    embedding: list[float]


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    score: float  # similarity score -- higher means more similar


@dataclass(frozen=True)
class SearchFilters:
    document_id: uuid.UUID | None = None
    document_type: str | None = None


class VectorStore(Protocol):
    name: str

    async def upsert(
        self, tenant_id: uuid.UUID, knowledge_base_id: uuid.UUID, records: list[VectorRecord]
    ) -> None: ...

    async def search(
        self,
        tenant_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        query_vector: list[float],
        *,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[VectorSearchResult]: ...
