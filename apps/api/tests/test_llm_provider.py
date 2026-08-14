"""Tests for llm/base.py (roadmap step 150). Same reasoning
test_embedding_provider.py/test_vectorstore_base.py already
established for this project's other interface-first steps: proves a
real class implementing exactly the documented Protocol shape works
the way the interface promises, not just that it type-checks.
"""

from dataclasses import dataclass

import pytest

from llm.base import LLMProvider, LLMResponse, Message


@dataclass
class _FakeLLMProvider:
    """A real implementation of LLMProvider -- not a mock of one --
    same reasoning _FakeEmbeddingProvider/_FakeVectorStore already
    established for this project's other provider interfaces."""

    name: str = "fake"

    async def complete(self, messages: list[Message]) -> LLMResponse:
        last_user_message = next(m for m in reversed(messages) if m.role == "user")
        return LLMResponse(
            content=f"echo: {last_user_message.content}",
            prompt_tokens=sum(len(m.content) for m in messages),
            completion_tokens=len(last_user_message.content),
        )


def test_fake_provider_satisfies_the_protocol_structurally() -> None:
    provider: LLMProvider = _FakeLLMProvider(name="fake")
    assert provider.name == "fake"


@pytest.mark.anyio
async def test_complete_returns_a_real_response_from_a_message_list() -> None:
    provider = _FakeLLMProvider()
    messages = [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="hello"),
    ]

    response = await provider.complete(messages)

    assert response.content == "echo: hello"
    assert response.completion_tokens == len("hello")
    assert response.prompt_tokens > 0


@pytest.mark.anyio
async def test_complete_on_a_multi_turn_conversation_uses_the_latest_user_message() -> None:
    provider = _FakeLLMProvider()
    messages = [
        Message(role="user", content="first"),
        Message(role="assistant", content="a reply"),
        Message(role="user", content="second"),
    ]

    response = await provider.complete(messages)

    assert response.content == "echo: second"
