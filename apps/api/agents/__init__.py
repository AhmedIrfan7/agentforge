"""Specialized agents (AGENTS.md SECTION 5: "a team of specialists
rather than one general-purpose assistant"). document_analysis.py (step
095) was the first; chunking_recommendation.py (step 097) is the
second.

base.py's Agent stayed deliberately minimal (just a `name` attribute,
no shared run() method) through step 097, extracted once a second real
agent existed to compare against the first, mirroring how OAuth was
built in this codebase: step 076 shipped a concrete Google
implementation with no interface at all, and step 077 generalized it
into a real Protocol + registry only once a second provider existed to
prove the abstraction was real. Comparing the two real agents here
showed the same pattern: they share an input type but do genuinely
different things with different, clearly-named methods, so name (for
logging/observability) was the only honest shared contract at the
time -- not a guess dressed up as one.

As of step 138, Agent gained a real, generic run()/config contract --
LangGraph (step 137) is the concrete reason: a graph node needs SOME
uniform way to invoke whatever agent it wraps, which no domain-
specific method name could give it. The three existing concrete agents
(document_analysis.py, chunking_recommendation.py, retriever.py) are
NOT retrofitted onto run() -- their own domain-specific methods stay
their real API, called directly outside any graph; a future step wraps
them for graph use only once something real needs to.

Still no Agent Registry/Orchestrator (also described in AGENTS.md's
SECTION 5) -- nothing in this codebase dynamically discovers or routes
between agents yet. Steps 139 (Agent Registry) and 140 (Orchestrator
service skeleton) are where that real need finally arrives.
"""
