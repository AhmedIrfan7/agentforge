"""Lexical reranker (roadmap step 125) -- the first, and (see
rerankers/__init__.py) only, real RerankerProvider. Term-overlap
scoring, not an ML cross-encoder or an LLM call -- same "don't
overclaim precision" stance as agents/chunking_recommendation.py's
structural scoring and agents/document_analysis.py's keyword
classifier: a real, working, honest technique, not a fabricated
confidence score standing in for one.

Score is recall-oriented: the fraction of the QUERY's unique tokens
that also appear in a candidate's text (`|query ∩ text| / |query|`),
not the reverse -- a candidate is relevant to the extent it covers
what the query is actually asking about, regardless of how much other,
unrelated text surrounds those terms (a long chunk containing every
query term shouldn't score worse than a short one just for having more
words). This is a genuinely different signal from both of this
project's other real ranking signals -- pgvector's cosine distance
(semantic, embedding-space) and Postgres's `ts_rank` (frequency/
position-weighted within one document's own tsvector) -- rather than a
weaker reimplementation of either: a plain second opinion asking "does
this candidate actually contain the words the query used," which
`ts_rank` doesn't directly answer (it can rank a document highly for
one rare matched term even if most of the query's other terms are
absent) and cosine similarity can't answer at all (it never looks at
the literal text).

Zero real dependency (no API key, no model download) -- unlike every
other real provider adapter in this codebase (openai.py embeddings,
google_oauth.py, etc.), this one works for real in every environment,
including one with no OPENAI_API_KEY, and needs no fake substituted in
for a live-server test the way dense_search's own tests do.
"""

import re
from dataclasses import dataclass

from rerankers.base import RerankCandidate, RerankResult

_TOKEN = re.compile(r"\w+")


def _tokenize(text: str) -> set[str]:
    return {match.group().lower() for match in _TOKEN.finditer(text)}


@dataclass
class LexicalReranker:
    name: str = "lexical"

    async def rerank(self, query: str, candidates: list[RerankCandidate]) -> list[RerankResult]:
        query_tokens = _tokenize(query)

        def _score(candidate: RerankCandidate) -> float:
            if not query_tokens:
                return 0.0
            candidate_tokens = _tokenize(candidate.text)
            overlap = len(query_tokens & candidate_tokens)
            return overlap / len(query_tokens)

        scored = [RerankResult(id=c.id, score=_score(c)) for c in candidates]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored
