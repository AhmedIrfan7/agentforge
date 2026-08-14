"""Citation Agent (roadmap step 149, AGENTS.md SECTION "CITATION
SYSTEM") -- unlike the five skeleton agents just before it (144-148),
this one gets a REAL `run()` implementation immediately: `citations.py`
:build_citations() already exists as real, working, tested logic
(step 127), so this is a thin adapter wrapping it for graph/agent use,
the same "wrap existing real logic behind the Agent interface, don't
rewrite it" pattern step 143 already used for `_RetrieverGraphAgent`
wrapping `agents/retriever.py:RetrieverAgent`.

`build_citations(chunks, *, document_info)` genuinely needs two
real inputs, both of which vary per call (unlike step 143's
`RetrieverAgent`, where `tenant_id`/`knowledge_base_id` were legitimately
stable, constructor-injectable config for a single request) -- there's
no honest "stable config vs. varying input" split here, so both are
bundled into one `CitationAgentInput`, satisfying `run()`'s real
single-input contract without inventing a fake split.

Unlike every step-143-through-148 agent, `CitationAgent` needs no
constructor arguments at all (`citations.py`'s own logic is a pure
function, no DB/provider dependency) -- it is genuinely stateless,
construct-once, call-many, exactly the shape `agents/registry.py:
AgentRegistry` (step 139) was designed for. It is not auto-registered
here, though: nothing in this codebase constructs-and-registers real
agents at app startup yet (the same reasoning `agents/memory.py`
onward avoided import-time registration side effects) -- a future
bootstrap step, once one exists, is where that would happen.
"""

import uuid
from dataclasses import dataclass

from agents.base import Agent
from citations import Citation, DocumentInfo, build_citations
from context_builder import ContextChunk


@dataclass(frozen=True)
class CitationAgentInput:
    chunks: list[ContextChunk]
    document_info: dict[uuid.UUID, DocumentInfo]


class CitationAgent(Agent[CitationAgentInput, list[Citation]]):
    name = "citation"

    async def run(self, input: CitationAgentInput) -> list[Citation]:
        return build_citations(input.chunks, document_info=input.document_info)
