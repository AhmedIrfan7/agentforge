"""Tests for embeddings/openai.py (roadmap step 107).

No real OpenAI API key is configured in this environment, so these use
httpx.MockTransport (built into httpx itself, no extra dependency) to
exercise the provider's actual request/response/error-handling logic
against a fake but realistic OpenAI response shape, instead of either
skipping this logic entirely or hitting the real paid API from a test
suite. This is a deliberate, documented gap from this project's usual
"live-verify against the real service" discipline (Google OAuth, ClamAV,
MinIO, etc.) -- real live verification needs a real OPENAI_API_KEY, which
isn't available here; see docs/ROADMAP.md's step 107 entry.
"""

import httpx
import pytest

from embeddings.openai import EmbeddingProviderError, OpenAIEmbeddingProvider


def _client_factory(handler: httpx.MockTransport) -> type[httpx.AsyncClient]:
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = handler
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    return _PatchedClient


@pytest.mark.anyio
async def test_embed_returns_vectors_in_input_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")
        assert str(request.url) == OpenAIEmbeddingProvider._EMBEDDINGS_URL
        return httpx.Response(
            200,
            json={
                "object": "list",
                # Deliberately out of order -- proves the provider sorts
                # by `index` rather than trusting response list order.
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [0.2, 0.2]},
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.1]},
                ],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    monkeypatch.setattr(
        "embeddings.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = OpenAIEmbeddingProvider()
    vectors = await provider.embed(["first", "second"])
    assert vectors == [[0.1, 0.1], [0.2, 0.2]]


@pytest.mark.anyio
async def test_embed_on_empty_input_returns_empty_output_without_a_request() -> None:
    provider = OpenAIEmbeddingProvider()
    assert await provider.embed([]) == []


@pytest.mark.anyio
async def test_embed_raises_provider_error_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    monkeypatch.setattr(
        "embeddings.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = OpenAIEmbeddingProvider()
    with pytest.raises(EmbeddingProviderError):
        await provider.embed(["text"])


@pytest.mark.anyio
async def test_embed_raises_provider_error_on_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "list"})  # missing "data"

    monkeypatch.setattr(
        "embeddings.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = OpenAIEmbeddingProvider()
    with pytest.raises(EmbeddingProviderError):
        await provider.embed(["text"])


def test_provider_declares_its_model_native_dimensions() -> None:
    provider = OpenAIEmbeddingProvider()
    assert provider.name == "openai"
    assert provider.dimensions == 1536
