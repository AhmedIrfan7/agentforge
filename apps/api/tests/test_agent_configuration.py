"""Tests for agents/configuration.py (roadmap step 158)."""

import pytest
from pydantic import ValidationError

from agents.configuration import KNOWN_AGENT_NAMES, AgentConfiguration


def test_default_configuration_is_valid_and_uses_real_defaults() -> None:
    config = AgentConfiguration()

    assert config.llm_provider == "openai"
    assert config.enabled_agents == ["retriever"]
    assert config.retrieval_top_k == 10


def test_accepts_the_second_real_llm_provider() -> None:
    config = AgentConfiguration(llm_provider="anthropic")

    assert config.llm_provider == "anthropic"


def test_rejects_an_unregistered_llm_provider() -> None:
    with pytest.raises(ValidationError, match="unknown LLM provider"):
        AgentConfiguration(llm_provider="cohere")


def test_accepts_a_real_multi_agent_list() -> None:
    config = AgentConfiguration(enabled_agents=["retriever", "citation", "safety"])

    assert config.enabled_agents == ["retriever", "citation", "safety"]


def test_rejects_an_unrecognized_agent_name() -> None:
    with pytest.raises(ValidationError, match="unknown agent name"):
        AgentConfiguration(enabled_agents=["retriever", "made_up_agent"])


def test_rejects_a_retrieval_top_k_below_the_real_minimum() -> None:
    with pytest.raises(ValidationError):
        AgentConfiguration(retrieval_top_k=0)


def test_rejects_a_retrieval_top_k_above_the_real_maximum() -> None:
    with pytest.raises(ValidationError):
        AgentConfiguration(retrieval_top_k=51)


def test_known_agent_names_excludes_ingestion_time_agents() -> None:
    assert "document_analysis" not in KNOWN_AGENT_NAMES
    assert "chunking_recommendation" not in KNOWN_AGENT_NAMES
    assert "retriever" in KNOWN_AGENT_NAMES


def test_round_trips_through_dict_serialization_for_a_future_jsonb_column() -> None:
    original = AgentConfiguration(
        llm_provider="anthropic", enabled_agents=["retriever", "reasoning"], retrieval_top_k=25
    )

    restored = AgentConfiguration.model_validate(original.model_dump())

    assert restored == original
