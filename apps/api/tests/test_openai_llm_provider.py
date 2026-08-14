"""Tests for llm/openai.py (roadmap step 151).

No real OpenAI API key is configured in this environment, so these use
httpx.MockTransport (same technique tests/test_openai_embedding_
provider.py already established at step 107) to exercise the
provider's actual request/response/error-handling logic against a
fake but realistic Chat Completions response shape. A real, live probe
against the actual api.openai.com endpoint was also run once (not
kept as a test -- would need a real paid key to assert anything
meaningful) and found a genuine, more precise failure mode than
expected: with `settings.openai_api_key` empty (this environment's
real state), `f"Bearer {settings.openai_api_key}"` becomes `"Bearer "`
with a trailing space, which httpx's own client-side header validation
rejects as `httpx.LocalProtocolError` *before* the request ever
reaches the network -- not a server-returned 401 as first assumed.
Confirmed live that `LocalProtocolError` is a real subclass of
`httpx.HTTPError`, so the existing `except (httpx.HTTPError, ...)`
clause already catches it correctly; the observable behavior (a clean,
generic `LLMProviderError`) is unaffected, this is a more precise
understanding of the exact mechanism, not a bug.
"""

import json

import httpx
import pytest

from llm.base import LLMProviderError, Message
from llm.openai import OpenAIProvider


def _client_factory(handler: httpx.MockTransport) -> type[httpx.AsyncClient]:
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = handler
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    return _PatchedClient


@pytest.mark.anyio
async def test_complete_returns_the_real_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")
        assert str(request.url) == OpenAIProvider._COMPLETIONS_URL
        payload = json.loads(request.read())
        assert payload["model"] == OpenAIProvider._MODEL
        assert payload["messages"] == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
        ]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "hi there"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            },
        )

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = OpenAIProvider()
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
async def test_complete_raises_provider_error_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = OpenAIProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete([Message(role="user", content="hi")])


@pytest.mark.anyio
async def test_complete_raises_provider_error_on_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})  # missing usage, empty choices

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = OpenAIProvider()
    with pytest.raises(LLMProviderError):
        await provider.complete([Message(role="user", content="hi")])


def test_provider_declares_its_name() -> None:
    assert OpenAIProvider().name == "openai"
