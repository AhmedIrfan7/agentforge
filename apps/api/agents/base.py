"""Agent base class/interface (roadmap step 138, AGENTS.md SECTION 5).

A real, uniform input/output/config contract, superseding the original
step-097 version of this file (`Agent` was just a `name: str`
attribute, no shared method) -- that version's own docstring already
reasoned about exactly this tradeoff: `DocumentAnalysisAgent` and
`ChunkingRecommendationAgent` had genuinely different domain-specific
methods (`.analyze()`, `.recommend()`), and forcing a shared `run()`
would have traded real clarity for a uniformity neither consumer
needed at the time. LangGraph (step 137) is the real, concrete reason
that calculus changes now: a graph node needs SOME uniform way to
invoke whatever agent it wraps, generic across agent types -- no
domain-specific method name can give a graph builder that.

Existing concrete agents (`DocumentAnalysisAgent`,
`ChunkingRecommendationAgent`, `agents/retriever.py:RetrieverAgent`)
are deliberately NOT retrofitted onto `run()` in this step -- their
own domain-specific methods stay their real, primary API, used
directly by their own real callers (extraction.py, routers/
retrieval.py) outside any graph, unchanged. Step 143 ("wire Retriever
Agent into orchestrator graph") is where a thin adapter wraps
`RetrieverAgent` to satisfy this interface for graph use specifically
-- the same "wrap existing real logic behind a new interface, don't
rewrite it" pattern step 124 itself used when `RetrieverAgent` wrapped
`routers/retrieval.py`'s own original inline logic. `run()` is
therefore NOT an abstractmethod: making it one would break every
existing subclass, none of which implement it and none of which are
being changed here -- it's a documented convention for new agents
(steps 144-149) to follow, the same "documented, not enforced" shape
`name` itself has always had on this class.

Generic over `InputT`/`OutputT` (PEP 695 type parameter syntax, same
convention `repositories/base.py:TenantScopedRepository[ModelT: ...]`
already established for this codebase's other generic base class --
not a fixed shape) -- forcing every future agent into a single
concrete input/output type would be speculative; each domain (memory,
conversation, reasoning, quality review, safety, citation) has its own
real shape.

`config` is a plain `dict[str, Any]`, not a schema-validated model yet
-- "per-agent execution tracing" (153) and "per-assistant agent-
configuration model" (158) are later, separate steps that will give
config real, validated structure once a real per-agent config shape
is known from an actual caller; nothing here should guess at that
shape today. `Agent.__init__` is additive, not a breaking change:
`DocumentAnalysisAgent`/`ChunkingRecommendationAgent` have no
`__init__` of their own (so `Agent()`'s new all-keyword-optional
signature is exactly what their existing zero-arg instantiation
already used), and `RetrieverAgent` defines its own `__init__` that
never calls `super().__init__()` -- its instances simply never get a
`.config` attribute, which is fine, since nothing reads it there.
"""

from typing import Any


class Agent[InputT, OutputT]:
    name: str

    def __init__(self, *, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    async def run(self, input: InputT) -> OutputT:
        raise NotImplementedError
