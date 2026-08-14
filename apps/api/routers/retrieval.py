"""Dense (vector similarity) retrieval endpoint (roadmap step 120) --
the first real caller of vectorstore/pgvector.py:PgVectorStore.search()
and embeddings/openai.py:OpenAIEmbeddingProvider.embed() (steps 107/119).

A free-text query has to become a vector before PgVectorStore.search()
can run anything -- this endpoint's own real job, beyond wiring, is
that one extra step: embed the query with the SAME provider that
embedded the chunks, since comparing vectors from two different
embedding models/dimensions would be meaningless. Own module-level
_embedding_provider singleton, same shape embeddings_pipeline.py's own
module-level instance already uses, rather than reaching into that
other module's underscore-prefixed (module-private) attribute --
there's exactly one real EmbeddingProvider in this codebase (checked at
step 107), so a second lightweight instance costs nothing and keeps
this module's own tests independent of embeddings_pipeline.py's.

Deliberately minimal response shape (DenseSearchResultRead: chunk_id/
document_id/text/score, nothing enriched with a document title or
metadata) -- this is the plumbing-proving step, not the polished,
product-facing search surface; step 133 ("Add knowledge-base search API
endpoint") is where a richer, client-ready shape belongs, once
reranking (125)/context-building (126)/citations (127) exist to justify
one. Reuses knowledge_base:read, not a new permission -- searching
within a knowledge base is a read action on that resource, same
"same capability, smaller/different view" reasoning steps 088/111
already established for document:read.

No real OPENAI_API_KEY exists in this environment (the same documented
gap as steps 107/108/111/112/113/114/117) -- a real search request here
fails closed with a plain 500 (errors.py's generic handler), which is
the honest shape for a genuine backend-dependency failure, not a
client-facing 4xx. This module's own _embedding_provider is swapped for
a fake in its tests, same established pattern
test_embeddings_pipeline.py already uses for its own module-level
provider.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from embeddings.base import EmbeddingProvider
from embeddings.openai import OpenAIEmbeddingProvider
from schemas.retrieval import DenseSearchRequest, DenseSearchResultRead
from vectorstore.pgvector import PgVectorStore

router = APIRouter(
    prefix=(
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}"
    ),
    tags=["retrieval"],
)

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]

_embedding_provider: EmbeddingProvider = OpenAIEmbeddingProvider()
_vector_store = PgVectorStore()


@router.post(
    "/search",
    response_model=list[DenseSearchResultRead],
    dependencies=[Depends(require_permission("knowledge_base:read"))],
)
async def dense_search(
    body: DenseSearchRequest,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> list[DenseSearchResultRead]:
    query_vectors = await _embedding_provider.embed([body.query])
    results = await _vector_store.search(
        tenant_id, knowledge_base.id, query_vectors[0], top_k=body.top_k
    )
    return [
        DenseSearchResultRead(
            chunk_id=r.chunk_id, document_id=r.document_id, text=r.text, score=r.score
        )
        for r in results
    ]
