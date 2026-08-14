"""RerankerProvider (roadmap step 125) -- a structural Protocol, same
reasoning embeddings/base.py:EmbeddingProvider and vectorstore/base.py:
VectorStore already established: nothing here needs inheritance or
shared state between implementations, each is a self-contained scoring
function over (query, candidates).

RerankCandidate/RerankResult are this package's own minimal shapes
(id/text in, id/score out) -- deliberately NOT agents.retriever.
RetrievedChunk. Reranking is a lower-level primitive than the Retriever
Agent (same layering as embeddings/vectorstore, both of which the
agent depends on, not the reverse) -- rerankers/ must not import from
agents/. A caller (agents/retriever.py or otherwise) maps its own
richer result type down to RerankCandidate before calling rerank(),
and maps RerankResult.score back onto its own objects by id
afterward -- the same "own real output shape, not borrowed from a
caller" reasoning vectorstore/base.py's VectorSearchResult and
embeddings/base.py's plain list[float] already use.

AGENTS.md's own "Design reranking as an independent stage" is taken
literally: rerank() is not folded into RetrieverAgent.search_dense/
search_keyword/search_hybrid (each of which already produces its own
real, meaningful ranking -- cosine distance, ts_rank, or RRF) --
instead it's a separate, explicit, opt-in stage a caller applies to
already-retrieved results, matching this step's own name ("Add
reranking step") as something ADDED to a pipeline, not baked into
retrieval itself.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RerankCandidate:
    id: uuid.UUID
    text: str


@dataclass(frozen=True)
class RerankResult:
    id: uuid.UUID
    score: float


class RerankerProvider(Protocol):
    name: str

    async def rerank(self, query: str, candidates: list[RerankCandidate]) -> list[RerankResult]: ...
