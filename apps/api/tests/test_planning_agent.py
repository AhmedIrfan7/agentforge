"""Tests for agents/planning.py (roadmap step 142)."""

import pytest

from agents.planning import Plan, PlanningAgent


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = PlanningAgent()
    assert agent.name == "planning"


@pytest.mark.anyio
async def test_document_search_intent_plans_to_run_the_retriever() -> None:
    agent = PlanningAgent()

    plan = await agent.run("document_search")

    assert plan.agent_names == ["retriever"]


@pytest.mark.anyio
async def test_empty_intent_plans_no_agents() -> None:
    agent = PlanningAgent()

    plan = await agent.run("empty")

    assert plan.agent_names == []


@pytest.mark.anyio
async def test_an_unrecognized_intent_plans_no_agents_rather_than_guessing() -> None:
    agent = PlanningAgent()

    plan = await agent.run("something_this_agent_has_never_seen")

    assert plan.agent_names == []


def test_plan_defaults_to_no_agents() -> None:
    assert Plan().agent_names == []
