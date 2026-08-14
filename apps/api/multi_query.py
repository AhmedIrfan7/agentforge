"""Multi-query retrieval (roadmap step 130, AGENTS.md "RETRIEVAL
STRATEGY" -- one of the named techniques to "evaluate ... and combine
... when beneficial"). Query expansion is a real, deterministic
heuristic here, not an LLM call: no chat/generation step exists yet in
this codebase to paraphrase a query with (steps 150+), and no real
OPENAI_API_KEY exists in this environment either -- same "honest
heuristic when a real ML/LLM technique doesn't exist yet" stance as
agents/chunking_recommendation.py, agents/document_analysis.py, and
rerankers/lexical.py.

A genuinely compound query ("refund policy and shipping times") is
really two separate asks bundled into one string -- splitting it into
its own clauses and retrieving for each separately, then fusing (see
agents/retriever.py:RetrieverAgent.search_multi_query), finds
documents that answer either half well even when no single document
(or embedding) covers both topics at once. A simple, non-compound
query expands to just itself: one variant, one retrieval call, the
same as calling the underlying search directly -- multi-query
retrieval never makes a simple query worse or slower.
"""

import re

_SPLIT_PATTERN = re.compile(r"\s+(?:and|or)\s+|[,;]\s*", re.IGNORECASE)

# An Oxford-comma list ("X, Y, and Z") splits its last clause off the
# comma before "and"/"or" is ever seen, leaving that clause reading
# "and Z" -- strip a leading conjunction left over from that case
# (verified live: a first draft without this left "and warranty
# coverage" as its own clause instead of "warranty coverage").
_LEADING_CONJUNCTION = re.compile(r"^(?:and|or)\s+", re.IGNORECASE)

# A real, stated bound -- an adversarial query with many conjunctions
# ("a and b and c and d and e and f") shouldn't fan out into an
# unbounded number of retrieval calls.
_MAX_VARIANTS = 5


def expand_query(query: str) -> list[str]:
    clauses = [clause.strip() for clause in _SPLIT_PATTERN.split(query) if clause.strip()]
    clauses = [_LEADING_CONJUNCTION.sub("", clause).strip() for clause in clauses]
    clauses = [clause for clause in clauses if clause]

    if len(clauses) <= 1:
        return [query]

    # The original (unsplit) query is included alongside its own
    # clauses -- the compound phrasing itself might match a document
    # that discusses both topics together, which retrieving only the
    # individual clauses could miss.
    variants = [query, *clauses]

    # Dedupe while preserving order -- a clause identical to the whole
    # query (e.g. a delimiter matched but produced no real second
    # clause) shouldn't count as a second variant.
    seen: set[str] = set()
    deduped: list[str] = []
    for variant in variants:
        key = variant.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(variant)

    return deduped[:_MAX_VARIANTS]
