"""OpenAI Whisper STT provider (roadmap step 217) -- the first real
`voice/base.py:SpeechToTextProvider`. Speaks OpenAI's Audio
Transcriptions REST API directly over httpx, same "a direct,
authenticated server-to-server call needs no vendor SDK for one
endpoint" reasoning `llm/openai.py`/`embeddings/openai.py` already
established for this project's other OpenAI adapters.

`POST /v1/audio/transcriptions` is multipart/form-data, not JSON --
the one OpenAI endpoint in this codebase that takes a file upload
rather than a JSON body. `model="whisper-1"` -- checked live (OpenAI's
own current API docs, 2026-08) before choosing: still listed as the
stable, real transcription model alongside newer options, the same
"cheapest/most stable current choice, not a speculative pick" reasoning
`llm/openai.py`/`embeddings/openai.py` already used for their own model
choices.

`response_format="verbose_json"`, not the plain-json default -- the
extra fields (`language`/`duration`/`segments`) are the ONLY way this
endpoint reports the detected language back, and
`TranscriptionResult.language` exists specifically to carry it; the
default response has no field for it at all.

OpenAI's own docs validate the uploaded file by its FILENAME
EXTENSION, not the multipart part's declared content-type -- so the
caller's real `mime_type` (e.g. `"audio/webm"` from a browser
`MediaRecorder`) is mapped to a matching filename
(`_filename_for_mime_type`) rather than a fixed placeholder name, or a
real caller's real webm/wav/mp4 recording would silently fail this
endpoint's own format check regardless of its actual, correct content.

Live-probed once against the real `api.openai.com` endpoint with no
API key configured (this environment's real state) -- same finding
`llm/openai.py`'s own docstring already documents: an empty
`settings.openai_api_key` makes `f"Bearer {...}"` become `"Bearer "`
with a trailing space, which httpx rejects client-side as
`httpx.LocalProtocolError` before any request reaches the network. A
real subclass of `httpx.HTTPError`, so `except (httpx.HTTPError,
KeyError)` already catches it correctly -- confirmed live, not
assumed to generalize from the Chat Completions endpoint's own
finding.
"""

import httpx

from config import settings
from voice.base import SpeechProviderError, TranscriptionResult


def _filename_for_mime_type(mime_type: str) -> str:
    subtype = mime_type.split("/")[-1].split(";")[0].strip()
    return f"audio.{subtype}"


class WhisperSTTProvider:
    name = "whisper"

    _TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
    _MODEL = "whisper-1"

    async def transcribe(self, audio: bytes, *, mime_type: str) -> TranscriptionResult:
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    self._TRANSCRIPTIONS_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    data={"model": self._MODEL, "response_format": "verbose_json"},
                    files={"file": (_filename_for_mime_type(mime_type), audio, mime_type)},
                )
                response.raise_for_status()
                payload = response.json()
                return TranscriptionResult(text=payload["text"], language=payload.get("language"))
            except (httpx.HTTPError, KeyError) as exc:
                raise SpeechProviderError("OpenAI Whisper transcription request failed.") from exc
