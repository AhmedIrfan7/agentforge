"""OpenAI TTS provider (roadmap step 218) -- the first real
`voice/base.py:TextToSpeechProvider`. Speaks OpenAI's own Text-to-
Speech REST API directly over httpx, same "no vendor SDK needed for
one endpoint" reasoning `llm/openai.py`/`embeddings/openai.py`/
`voice/whisper.py` already established -- OpenAI, not a second vendor
(ElevenLabs, etc.), keeps this codebase depending on one real speech
vendor/API key it already has, rather than adding a second this
roadmap's own sequence never asks for.

`POST /v1/audio/speech`, JSON body (unlike `voice/whisper.py`'s own
multipart upload -- this endpoint takes text in, not a file). Checked
live (OpenAI's own current API docs, 2026-08) before choosing
`model="tts-1"` over the newer `gpt-4o-mini-tts`: comparably priced,
but `tts-1` is OpenAI's own documented lower-latency option (`tts-1-hd`
trades latency for quality) -- the right tradeoff for a real-time
voice conversation, matching AGENTS.md's own "VOICE BOT EXPERIENCE"
section naming "Fast response time" outright. `voice="alloy"` (OpenAI's
own default/example voice) is a fixed constant, not a per-call
parameter -- `TextToSpeechProvider.synthesize` deliberately takes no
voice argument yet (216's own "add the parameter when a real step
needs it" discipline); nothing through step 232 asks for voice
selection.

The response body IS the raw audio itself (unlike every other OpenAI
endpoint this codebase talks to, which returns JSON) -- `SynthesisResult
.content_type` is read from the response's own real `Content-Type`
header rather than hardcoded, since that's the provider's own honest
report of what it actually sent back, not an assumption this codebase
makes about response_format's effect.

Known, honest limitation not handled here: OpenAI's real input-length
cap (4,096 characters) is not validated or chunked client-side -- no
real caller through this roadmap's own current sequence sends text
anywhere near that long yet; if a future step's real usage needs
chunking, add it then; validating it now would be guessing at a
constraint no real caller has hit.

Live-probed once against the real `api.openai.com` endpoint with no
API key configured -- the third confirmation this session of the same
`httpx.LocalProtocolError`-from-empty-bearer-token finding
`llm/openai.py`'s docstring first documented, now verified across
Chat Completions (JSON), Audio Transcriptions (multipart upload), and
this endpoint (JSON in, raw bytes out) -- a real, consistent property
of this codebase's own `f"Bearer {settings.openai_api_key}"` pattern
wherever it's used, not endpoint-shape-specific.
"""

import httpx

from config import settings
from voice.base import SpeechProviderError, SynthesisResult


class OpenAITTSProvider:
    name = "openai-tts"

    _SPEECH_URL = "https://api.openai.com/v1/audio/speech"
    _MODEL = "tts-1"
    _VOICE = "alloy"

    async def synthesize(self, text: str) -> SynthesisResult:
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    self._SPEECH_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={
                        "model": self._MODEL,
                        "input": text,
                        "voice": self._VOICE,
                        "response_format": "mp3",
                    },
                )
                response.raise_for_status()
                content_type = response.headers.get("content-type", "audio/mpeg")
                return SynthesisResult(audio=response.content, content_type=content_type)
            except httpx.HTTPError as exc:
                raise SpeechProviderError("OpenAI TTS synthesis request failed.") from exc
