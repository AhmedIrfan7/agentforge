"""Precision@k / recall@k (roadmap step 128) -- the standard information-
retrieval formulas, not something to verify live the way a third-party
library's API surface would be (this codebase's usual "verify before
trusting" discipline applies to unfamiliar external behavior, not to
well-known math): precision is the fraction of the top-k retrieved
items that are relevant, recall is the fraction of all relevant items
that made it into the top-k.

Operate on generic `uuid.UUID` ids, not any retrieval-specific result
type (RetrievedChunk, etc.) -- same layering reasoning rerankers/
base.py and context_builder.py already established: a pure metrics
module has no business depending on agents/ or any richer domain type,
a caller extracts the ids itself before calling in.
"""

import uuid


def precision_at_k(retrieved_ids: list[uuid.UUID], relevant_ids: set[uuid.UUID], k: int) -> float:
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for id_ in top_k if id_ in relevant_ids)
    return hits / len(top_k)


def recall_at_k(retrieved_ids: list[uuid.UUID], relevant_ids: set[uuid.UUID], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for id_ in top_k if id_ in relevant_ids)
    return hits / len(relevant_ids)
