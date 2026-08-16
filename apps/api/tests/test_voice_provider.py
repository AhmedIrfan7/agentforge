"""Tests for voice/base.py (roadmap step 216). Same reasoning
test_llm_provider.py/test_embedding_provider.py already established for
this project's other interface-first steps: proves real classes
implementing exactly the documented Protocol shapes work the way the
interfaces promise, not just that they type-check.
"""

from dataclasses import dataclass

import pytest

from voice.base import (
    SpeechToTextProvider,
    SynthesisResult,
    TextToSpeechProvider,
    TranscriptionResult,
)


@dataclass
class _FakeSpeechToTextProvider:
    """A real implementation of SpeechToTextProvider -- not a mock of
    one -- same reasoning _FakeLLMProvider already established."""

    name: str = "fake-stt"

    async def transcribe(self, audio: bytes, *, mime_type: str) -> TranscriptionResult:
        return TranscriptionResult(text=f"transcribed {len(audio)} bytes of {mime_type}")


@dataclass
class _FakeTextToSpeechProvider:
    name: str = "fake-tts"

    async def synthesize(self, text: str) -> SynthesisResult:
        return SynthesisResult(audio=text.encode(), content_type="audio/mpeg")


def test_fake_stt_provider_satisfies_the_protocol_structurally() -> None:
    provider: SpeechToTextProvider = _FakeSpeechToTextProvider(name="fake-stt")
    assert provider.name == "fake-stt"


def test_fake_tts_provider_satisfies_the_protocol_structurally() -> None:
    provider: TextToSpeechProvider = _FakeTextToSpeechProvider(name="fake-tts")
    assert provider.name == "fake-tts"


@pytest.mark.anyio
async def test_transcribe_returns_a_real_result_from_real_audio_bytes() -> None:
    provider = _FakeSpeechToTextProvider()
    audio = b"\x00\x01\x02\x03"

    result = await provider.transcribe(audio, mime_type="audio/webm")

    assert result.text == "transcribed 4 bytes of audio/webm"
    assert result.language is None


@pytest.mark.anyio
async def test_synthesize_returns_real_audio_bytes_from_text() -> None:
    provider = _FakeTextToSpeechProvider()

    result = await provider.synthesize("hello there")

    assert result.audio == b"hello there"
    assert result.content_type == "audio/mpeg"
