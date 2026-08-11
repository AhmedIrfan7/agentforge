"""Specialized agents (AGENTS.md SECTION 5: "a team of specialists
rather than one general-purpose assistant"). document_analysis.py (step
095) was the first; chunking_recommendation.py (step 097) is the
second.

base.py's Agent is deliberately minimal -- just a `name` attribute, no
shared run() method -- extracted once a second real agent existed to
compare against the first, mirroring how OAuth was built in this
codebase: step 076 shipped a concrete Google implementation with no
interface at all, and step 077 generalized it into a real Protocol +
registry only once a second provider existed to prove the abstraction
was real. Comparing the two real agents here showed the same pattern:
they share an input type but do genuinely different things with
different, clearly-named methods, so name (for logging/observability)
is the only honest shared contract -- not a guess dressed up as one.

Still no Agent Registry/Orchestrator (also described in AGENTS.md's
SECTION 5) -- nothing in this codebase dynamically discovers or routes
between agents yet; both existing agents are called directly from
extraction.py:_run_extraction. Build that machinery when something
actually needs to choose between agents at runtime, not before.
"""
