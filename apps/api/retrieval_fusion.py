"""Reciprocal Rank Fusion (roadmap step 122) -- combines dense (step
120) and keyword (step 121) search results into one ranked list.

Verified before trusting it, not assumed: RRF is the real, widely-
adopted technique for exactly this problem (Elasticsearch's own `rrf`
retriever, OpenSearch, Weaviate, and Qdrant's hybrid search all use
it), specifically because it operates on RANK POSITION, not raw score
-- cosine similarity (roughly [-1, 1]) and ts_rank (an unbounded,
document-length-and-term-frequency-dependent scale) aren't
comparable numbers, so combining them by weighted score would need a
normalization step this project would otherwise have to invent and
justify. RRF sidesteps that entirely: a chunk's contribution from each
ranked list is 1/(k + rank), summed across every list it appears in.

k=60 is the standard smoothing constant from the original RRF paper,
also what every production system above defaults to -- not a value
this project is choosing freely, since inventing a different one with
no data to justify it would be worse than using the field's own
established default.
"""

import uuid

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[uuid.UUID]], *, k: int = RRF_K
) -> dict[uuid.UUID, float]:
    """Each entry in `rankings` is one retriever's own results, already
    in rank order (best first) -- rank is derived from list position
    (1-indexed), not passed in separately, since that's the only thing
    RRF actually needs from a ranked list."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores
