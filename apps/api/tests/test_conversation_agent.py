"""Tests for agents/conversation.py -- real implementation now that a
real chat/generation model (llm/openai.py, step 151) exists to give it
one. Proves the real behavior: grounded prompting from real retrieved
chunks, the honest "no documents found" placeholder when there are
none, and that AgentRegistry now reports it healthy (run() really is
overridden, not the inherited NotImplementedError stub these tests
proved before this step)."""

import uuid
from dataclasses import dataclass, field

import pytest

from agents.base import Agent
from agents.conversation import ConversationAgent, ConversationInput
from agents.registry import AgentRegistry
from agents.retriever import RetrievedChunk
from llm.base import LLMResponse, Message


@dataclass
class _RecordingLLMProvider:
    """A real LLMProvider that records exactly what it was called with,
    so tests can assert on real prompt construction -- not a mock of the
    interface, a real implementation of it (test_llm_provider.py's own
    _FakeLLMProvider precedent)."""

    name: str = "fake"
    response_content: str = "a real answer"
    received_messages: list[list[Message]] = field(default_factory=list)

    async def complete(self, messages: list[Message]) -> LLMResponse:
        self.received_messages.append(messages)
        return LLMResponse(content=self.response_content, prompt_tokens=10, completion_tokens=5)


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), text=text, score=0.9)


def test_agent_satisfies_the_base_agent_shape() -> None:
    agent = ConversationAgent(_RecordingLLMProvider())
    assert agent.name == "conversation"


def test_run_is_overridden_for_real() -> None:
    assert type(ConversationAgent(_RecordingLLMProvider())).run is not Agent.run


def test_registering_it_now_reports_as_healthy() -> None:
    registry = AgentRegistry()
    registry.register(ConversationAgent(_RecordingLLMProvider()))

    assert registry.discover() == ["conversation"]
    assert registry.health_check() == {"conversation": True}


@pytest.mark.anyio
async def test_run_returns_the_real_llm_response_verbatim() -> None:
    provider = _RecordingLLMProvider(response_content="Ahmed has React and FastAPI experience.")
    agent = ConversationAgent(provider)

    result = await agent.run(ConversationInput(query="skills?", chunks=[_chunk("React, FastAPI")]))

    assert isinstance(result, LLMResponse)
    assert result.content == "Ahmed has React and FastAPI experience."
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5


@pytest.mark.anyio
async def test_run_includes_real_chunk_text_in_the_prompt_sent_to_the_llm() -> None:
    provider = _RecordingLLMProvider()
    agent = ConversationAgent(provider)

    await agent.run(
        ConversationInput(
            query="what languages does he know",
            chunks=[_chunk("Languages: Python, JavaScript"), _chunk("Backend: FastAPI")],
        )
    )

    assert len(provider.received_messages) == 1
    sent = provider.received_messages[0]
    system_message = next(m for m in sent if m.role == "system")
    user_message = next(m for m in sent if m.role == "user")
    assert "ONLY the context" in system_message.content
    assert "Python, JavaScript" in user_message.content
    assert "FastAPI" in user_message.content
    assert "what languages does he know" in user_message.content


@pytest.mark.anyio
async def test_run_with_no_chunks_still_calls_the_llm_with_an_honest_placeholder() -> None:
    provider = _RecordingLLMProvider(response_content="I don't have information about that.")
    agent = ConversationAgent(provider)

    result = await agent.run(ConversationInput(query="does he have a PhD", chunks=[]))

    assert result.content == "I don't have information about that."
    sent_user_message = next(m for m in provider.received_messages[0] if m.role == "user")
    assert "no relevant documents were found" in sent_user_message.content
