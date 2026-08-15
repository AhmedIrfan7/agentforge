"""Per-assistant agent-configuration model (roadmap step 158,
AGENTS.md's own "AI ASSISTANTS" section: "Each assistant should
have:... Agent configuration...").

Deliberately scoped to just this ONE bullet from that section's list --
Name/Description/Instructions/Knowledge access/Voice configuration/
Memory settings/Security policies/Deployment settings/Analytics/Future
tool integrations are each a separate, later concern, not this step's
job. The `Assistant` DB model itself doesn't exist until step 159 --
`AgentConfiguration` is built now as a standalone, validated Pydantic
model precisely so that step has a real, already-tested shape to
store, most likely as a JSONB column: the same "validated structure
over an untyped dict" preference `models/document.py`'s own
`doc_metadata` JSONB column already established for genuinely
multi-field, flexible per-record data. Pydantic (not a plain
dataclass, unlike most of this codebase's other agents/ data shapes --
`RetrievedChunk`, `Plan`, `AgentExecutionTrace`, `AgentStepResult`) is
the right base specifically because real field validation is the
point of this step, not just a container.

Lives in `agents/`, not `schemas/`, on purpose: it needs to read each
real agent's own `.name` class attribute and `llm.PROVIDERS`' real
keys, and `schemas/` is a router-facing DTO layer that must not import
from `agents/` (the same "provider/transform packages never import
from agents/ or schemas/" layering rule this codebase already
enforces, applied here in its normal direction -- agents/ importing
llm/ and other agents/ classes is already established, e.g. agents/
retriever.py's own EmbeddingProvider/VectorStore imports). A future
`schemas/assistant.py` (159/160) can import THIS module -- that
direction is fine.

`llm_provider` is validated against `llm.PROVIDERS`' real, live keys
(152) rather than a hardcoded Literal -- a hardcoded list would
silently drift the moment a third provider is added; this can't.

`enabled_agents` is validated against KNOWN_AGENT_NAMES, sourced
directly from each real, request-time agent's own `.name` class
attribute (not restated string literals, for the same no-drift
reason) -- scoped to the agents `orchestrator.py`'s own request flow
actually runs (retriever/citation/planning/memory/conversation/
reasoning/quality_review/safety), deliberately excluding
`document_analysis`/`chunking_recommendation` -- both real agents, but
ingestion-time, never part of an assistant's own runtime request path.
Naming an agent here doesn't promise it does anything yet: five of
those eight (144-148) are still honest `NotImplementedError`
skeletons -- this model validates that a configured name is REAL and
RECOGNIZED, not that the agent behind it is fully implemented.

`retrieval_top_k` reuses RetrieverAgent's own real, already-used
`top_k` parameter (120+) -- the one per-agent tuning knob this
codebase's retrieval path genuinely honors today.
"""

from pydantic import BaseModel, Field, field_validator

from agents.citation import CitationAgent
from agents.conversation import ConversationAgent
from agents.memory import MemoryAgent
from agents.planning import PlanningAgent
from agents.quality_review import QualityReviewAgent
from agents.reasoning import ReasoningAgent
from agents.retriever import RetrieverAgent
from agents.safety import SafetyAgent
from llm import PROVIDERS

KNOWN_AGENT_NAMES: frozenset[str] = frozenset(
    {
        RetrieverAgent.name,
        CitationAgent.name,
        PlanningAgent.name,
        MemoryAgent.name,
        ConversationAgent.name,
        ReasoningAgent.name,
        QualityReviewAgent.name,
        SafetyAgent.name,
    }
)


class AgentConfiguration(BaseModel):
    llm_provider: str = "openai"
    enabled_agents: list[str] = Field(default_factory=lambda: ["retriever"])
    retrieval_top_k: int = Field(default=10, ge=1, le=50)

    @field_validator("llm_provider")
    @classmethod
    def _llm_provider_must_be_a_real_provider(cls, value: str) -> str:
        if value not in PROVIDERS:
            raise ValueError(f"unknown LLM provider {value!r}; must be one of {sorted(PROVIDERS)}")
        return value

    @field_validator("enabled_agents")
    @classmethod
    def _enabled_agents_must_be_known_names(cls, value: list[str]) -> list[str]:
        unknown = [name for name in value if name not in KNOWN_AGENT_NAMES]
        if unknown:
            raise ValueError(
                f"unknown agent name(s) {unknown!r}; "
                f"must be a subset of {sorted(KNOWN_AGENT_NAMES)}"
            )
        return value
