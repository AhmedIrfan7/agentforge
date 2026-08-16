"""Speech-provider abstraction (roadmap step 216, AGENTS.md's own
"VOICE BOT EXPERIENCE" section: "Support multiple providers if
possible"). Same interface-first precedent `llm/base.py:LLMProvider`
(150) and `embeddings/base.py:EmbeddingProvider` (106) already
established for this codebase: the abstraction lands before any
concrete implementation (217 Whisper STT, 218 TTS), a structural
`Protocol` rather than an ABC for the same "a consistent shape, not
inheritance/shared state" reasoning `auth/oauth.py:OAuthProvider` (077)
already used.

Two separate Protocols, not one combined "speech provider" -- a real
STT provider (e.g. Whisper) and a real TTS provider (e.g. ElevenLabs/
OpenAI TTS) are commonly two entirely different vendors/APIs in
practice, and nothing in this roadmap's own sequencing (216-232) ever
asks for one implementation backing both directions.

Both methods are deliberately non-streaming (`bytes` in, one result
out) -- streaming audio ingestion (221) and streaming TTS output (222)
are explicit LATER steps in this exact milestone; adding streaming
methods now would be speculating ahead of the step that actually needs
them, the same "add the method when the step that needs it lands"
discipline `llm/base.py`'s own docstring already states outright for
this project. `mime_type` is a required parameter on `transcribe`, not
assumed -- a real caller (a browser's `MediaRecorder`, or a future
telephony integration) can hand back different real audio container
formats, and a provider needs to know which one it's decoding.

No `PROVIDERS` registry dict yet, unlike `llm/__init__.py`'s own
(152) -- that dict deliberately landed at LLM's *second* concrete
provider, not its first (077's own "don't build machinery before
there's a second real entry to put in it" discipline). Voice's own
roadmap sequence (216-232) never names a second STT or TTS provider,
so a registry here would be dead, untested machinery with nothing
real to put in it; if a second provider is ever added outside this
roadmap's own sequence, add the registry then, matching how it's
always been done in this codebase.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None = None


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    content_type: str


class SpeechProviderError(Exception):
    """A single error type for any real STT/TTS provider failure (auth,
    rate limit, network, malformed audio, unsupported format) -- same
    "one thing a future dispatcher can catch regardless of which
    provider is behind the interface" reasoning as
    `llm/base.py:LLMProviderError`."""


class SpeechToTextProvider(Protocol):
    name: str

    async def transcribe(self, audio: bytes, *, mime_type: str) -> TranscriptionResult: ...


class TextToSpeechProvider(Protocol):
    name: str

    async def synthesize(self, text: str) -> SynthesisResult: ...
