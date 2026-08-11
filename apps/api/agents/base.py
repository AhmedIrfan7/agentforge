"""Minimal shared Agent base (AGENTS.md SECTION 5), extracted now that a
second real agent exists to compare against the first -- see agents/
__init__.py for why this deliberately didn't happen preemptively at
step 095.

Only `name` turns out to be genuinely shared between
DocumentAnalysisAgent.analyze(text) -> DocumentAnalysisResult and
ChunkingRecommendationAgent.recommend(text) -> ChunkingRecommendation
(step 097): both take the same input type, but they're real, different
operations with clearly different, domain-specific method names --
forcing them behind one generic run() would trade real clarity for a
uniformity neither consumer actually needs. name exists for AGENTS.md's
Agent Design Principles' "independent logging" -- a consistent tag to
log/monitor by, not a behavioral contract every agent must implement
identically.
"""


class Agent:
    name: str
