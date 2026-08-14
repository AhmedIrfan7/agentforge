"""Tests for agents/citation.py (roadmap step 149) -- proves the
wiring, not re-deriving citations.py:build_citations()'s own already-
tested correctness (test_citations.py, step 127). Also the first real
agent this codebase can register as genuinely healthy, unlike the
five skeletons before it (144-148)."""

import uuid

import pytest

from agents.base import Agent
from agents.citation import CitationAgent, CitationAgentInput
from agents.registry import AgentRegistry
from citations import DocumentInfo
from context_builder import ContextChunk


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = CitationAgent()
    assert agent.name == "citation"


def test_run_is_a_real_override_unlike_the_skeleton_agents() -> None:
    assert type(CitationAgent()).run is not Agent.run


@pytest.mark.anyio
async def test_run_delegates_to_the_real_build_citations() -> None:
    document_id = uuid.uuid4()
    chunk = ContextChunk(
        id=uuid.uuid4(), document_id=document_id, text="## Refund Policy\n\nDetails here."
    )
    document_info = {document_id: DocumentInfo(title="policy.pdf", knowledge_base_name="Support")}

    citations = await CitationAgent().run(
        CitationAgentInput(chunks=[chunk], document_info=document_info)
    )

    assert len(citations) == 1
    assert citations[0].chunk_id == chunk.id
    assert citations[0].document_title == "policy.pdf"
    assert citations[0].knowledge_base_name == "Support"
    assert citations[0].section == "Refund Policy"


@pytest.mark.anyio
async def test_run_on_empty_chunks_returns_empty_citations() -> None:
    citations = await CitationAgent().run(CitationAgentInput(chunks=[], document_info={}))
    assert citations == []


def test_registering_it_reports_as_healthy() -> None:
    """The real payoff of AgentRegistry.health_check() (step 139)
    finally showing True: unlike agents/memory.py onward, this agent
    genuinely implements run()."""
    registry = AgentRegistry()
    registry.register(CitationAgent())

    assert registry.discover() == ["citation"]
    assert registry.health_check() == {"citation": True}
