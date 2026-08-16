"""Tests for voice/whisper.py (roadmap step 217).

No real OpenAI API key is configured in this environment, so these use
httpx.MockTransport (same technique test_openai_llm_provider.py/
test_openai_embedding_provider.py already established) to exercise the
provider's actual request/response/error-handling logic against a
fake but realistic Audio Transcriptions response shape.
"""

import httpx
import pytest

from voice.base import SpeechProviderError
from voice.whisper import WhisperSTTProvider, _filename_for_mime_type


def _client_factory(handler: httpx.MockTransport) -> type[httpx.AsyncClient]:
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = handler
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    return _PatchedClient


@pytest.mark.parametrize(
    ("mime_type", "expected_filename"),
    [
        ("audio/webm", "audio.webm"),
        ("audio/webm;codecs=opus", "audio.webm"),
        ("audio/wav", "audio.wav"),
        ("audio/mp4", "audio.mp4"),
    ],
)
def test_filename_for_mime_type_derives_a_real_matching_extension(
    mime_type: str, expected_filename: str
) -> None:
    assert _filename_for_mime_type(mime_type) == expected_filename


@pytest.mark.anyio
async def test_transcribe_returns_the_real_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")
        assert str(request.url) == WhisperSTTProvider._TRANSCRIPTIONS_URL
        body = request.read()
        assert b'name="model"' in body
        assert b"whisper-1" in body
        assert b'name="response_format"' in body
        assert b"verbose_json" in body
        assert b'filename="audio.webm"' in body
        return httpx.Response(
            200,
            json={
                "task": "transcribe",
                "language": "english",
                "duration": 1.2,
                "text": "hello there",
            },
        )

    monkeypatch.setattr(
        "voice.whisper.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = WhisperSTTProvider()

    result = await provider.transcribe(b"\x00\x01fakeaudio", mime_type="audio/webm")

    assert result.text == "hello there"
    assert result.language == "english"


@pytest.mark.anyio
async def test_transcribe_raises_provider_error_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    monkeypatch.setattr(
        "voice.whisper.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = WhisperSTTProvider()
    with pytest.raises(SpeechProviderError):
        await provider.transcribe(b"audio", mime_type="audio/wav")


@pytest.mark.anyio
async def test_transcribe_raises_provider_error_on_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"task": "transcribe"})  # missing "text"

    monkeypatch.setattr(
        "voice.whisper.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )
    provider = WhisperSTTProvider()
    with pytest.raises(SpeechProviderError):
        await provider.transcribe(b"audio", mime_type="audio/wav")


def test_provider_declares_its_name() -> None:
    assert WhisperSTTProvider().name == "whisper"
