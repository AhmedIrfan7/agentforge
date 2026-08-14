"""Tests for llm/anthropic.py (roadmap step 152).

Same httpx.MockTransport technique test_openai_llm_provider.py already
established at step 151: exercises the provider's real request/
response/error-handling logic against a fake but realistic Messages
API response shape, without needing a real paid key. Additionally
covers the two real, confirmed-live shape differences from OpenAI this
provider has to handle itself: `system` as a top-level parameter
rather than a message role, and `content` as an array of typed blocks
rather than a single string.
"""

import json

import httpx
import pytest

from llm.anthropic import AnthropicProvider
from llm.base import LLMProviderError, Message


def _client_factory(handler: httpx.MockTransport) -> type[httpx.AsyncClient]:
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = handler
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    return _PatchedClient


@pytest.mark.anyio
async def test_complete_splits_system_message_into_top_level_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == ""
        assert request.headers["anthropic-version"] == AnthropicProvider._ANTHROPIC_VERSION
        assert str(request.url) == AnthropicProvider._MESSAGES_URL
        payload = json.loads(request.read())
        assert payload["model"] == AnthropicProvider._MODEL
        assert payload["max_tokens"] == AnthropicProvider._MAX_TOKENS
        assert payload["system"] == "You are helpful."
        assert payload["messages"] == [{"role": "user", "content": "hello"}]
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "hi there"}],
                "usage": {"input_tokens": 12, "output_tokens": 3},
            },
        )

    monkeypatch.setattr(
        "llm.anthropic.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = AnthropicProvider()
    response = await provider.complete(
        [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="hello"),
        ]
    )

    assert response.content == "hi there"
    assert response.prompt_tokens == 12
    assert response.completion_tokens == 3


@pytest.mark.anyio
async def test_complete_omits_system_parameter_when_no_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert "system" not in payload
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    monkeypatch.setattr(
        "llm.anthropic.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = AnthropicProvider()
    await provider.complete([Message(role="user", content="hi")])


@pytest.mark.anyio
async def test_complete_picks_the_first_text_block_from_a_mixed_content_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "noop", "input": {}},
                    {"type": "text", "text": "the real answer"},
                ],
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )

    monkeypatch.setattr(
        "llm.anthropic.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = AnthropicProvider()
    response = await provider.complete([Message(role="user", content="hi")])

    assert response.content == "the real answer"


@pytest.mark.anyio
async def test_complete_raises_provider_error_when_no_text_block_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "id": "toolu_1", "name": "noop", "input": {}}],
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )

    monkeypatch.setattr(
        "llm.anthropic.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = AnthropicProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete([Message(role="user", content="hi")])


@pytest.mark.anyio
async def test_complete_raises_provider_error_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"type": "authentication_error"}})

    monkeypatch.setattr(
        "llm.anthropic.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = AnthropicProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete([Message(role="user", content="hi")])


@pytest.mark.anyio
async def test_complete_raises_provider_error_on_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": []})  # missing usage entirely

    monkeypatch.setattr(
        "llm.anthropic.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = AnthropicProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete([Message(role="user", content="hi")])


def test_provider_declares_its_name() -> None:
    assert AnthropicProvider().name == "anthropic"
