"""Tests for voice/openai_tts.py (roadmap step 218).

No real OpenAI API key is configured in this environment, so these use
httpx.MockTransport (same technique test_openai_llm_provider.py/
test_whisper_stt_provider.py already established) to exercise the
provider's actual request/response/error-handling logic against a
fake but realistic Text-to-Speech response shape.
"""

import json

import httpx
import pytest

from voice.base import SpeechProviderError
from voice.openai_tts import OpenAITTSProvider


def _client_factory(handler: httpx.MockTransport) -> type[httpx.AsyncClient]:
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = handler
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    return _PatchedClient


@pytest.mark.anyio
async def test_synthesize_returns_the_real_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")
        assert str(request.url) == OpenAITTSProvider._SPEECH_URL
        payload = json.loads(request.read())
        assert payload["model"] == OpenAITTSProvider._MODEL
        assert payload["input"] == "hello there"
        assert payload["voice"] == OpenAITTSProvider._VOICE
        assert payload["response_format"] == "mp3"
        return httpx.Response(
            200,
            content=b"\xff\xfbfake-mp3-bytes",
            headers={"content-type": "audio/mpeg"},
        )

    monkeypatch.setattr(
        "voice.openai_tts.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = OpenAITTSProvider()

    result = await provider.synthesize("hello there")

    assert result.audio == b"\xff\xfbfake-mp3-bytes"
    assert result.content_type == "audio/mpeg"


@pytest.mark.anyio
async def test_synthesize_raises_provider_error_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    monkeypatch.setattr(
        "voice.openai_tts.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = OpenAITTSProvider()
    with pytest.raises(SpeechProviderError):
        await provider.synthesize("hi")


def test_provider_declares_its_name() -> None:
    assert OpenAITTSProvider().name == "openai-tts"
