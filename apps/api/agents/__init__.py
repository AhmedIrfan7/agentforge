"""Specialized agents (AGENTS.md SECTION 5: "a team of specialists
rather than one general-purpose assistant"). document_analysis.py
(roadmap step 095) is the first one.

No shared Agent base class/interface yet, and no Agent Registry/
Orchestrator (both described in AGENTS.md's SECTION 5) -- this project
has exactly one real agent as of step 095, with a second already known
to be coming (097's Chunking Recommendation Agent). This mirrors how
OAuth was built in this codebase: step 076 shipped a concrete Google
implementation with no interface at all; step 077 generalized it into a
real Protocol + registry only once a second provider existed to prove
the abstraction was real, not a guess dressed up as one. Extract a
shared Agent shape here the same way, once 097 lands and there are two
real agents to compare -- not preemptively, from the shape of one.
"""
