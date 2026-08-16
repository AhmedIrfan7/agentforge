"""Voice-turn latency instrumentation (roadmap step 227). AGENTS.md's
own "VOICE AGENT" section names "Latency optimization" as a real
responsibility, and "VOICE BOT EXPERIENCE" names "Fast response time"
outright -- neither is measurable without a real number to look at.

Same "wrap the real call site with one structured log event" shape
`agents/tracing.py`'s own `traced_run` (153) and `agents/retriever.py`'s
own `_log_retrieval` (129) already established -- generalized here to
voice's own real stages rather than an `Agent.run()` call, since
`SpeechToTextProvider`/`TextToSpeechProvider` aren't `Agent` subclasses.

Two separate trace events, not one, because they happen at genuinely
different points in a real turn's own real timeline: `log_turn_
processing` covers the SYNCHRONOUS portion of `_finalize_turn`
(transcription through reply generation) -- the real time a user waits
in silence before hearing anything back, the single number "Fast
response time" cares about most. `log_synthesis` covers `_stream_
synthesis`'s own real provider-call latency separately, since step 225
made synthesis a decoupled background task -- it no longer runs inside
the same synchronous window `_finalize_turn`'s own timing measures, and
can be cancelled mid-flight by a real barge-in (`status="interrupted"`,
a real, honest third outcome distinct from success/failure -- a fast
interruption isn't a slow synthesis, and conflating the two would make
real latency numbers meaningless for anyone reading them later,
including step 231's own future benchmark script).

Real, not synthetic: `tts_latency_ms` times the actual
`TextToSpeechProvider.synthesize()` provider call, not the chunked-
send-over-websocket loop after it -- OpenAI's own TTS API already
returns one complete, non-streaming response (`voice/openai_tts.py`'s
own docstring), so the entire audio is available the instant the
provider call returns; the local memory-to-socket chunking after that
is near-instant and not a meaningful latency signal worth reporting
separately.

Rate-limited turns are deliberately NOT traced here -- being rejected
isn't a latency measurement, it's a different concern
(`rate_limit.py`'s own job), and tracing it here would conflate "how
fast did a real turn complete" with "was this turn allowed to run at
all."
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class VoiceTurnProcessingTrace:
    voice_session_id: uuid.UUID
    status: Literal["success", "failure"]
    stt_latency_ms: float
    reply_latency_ms: float | None
    total_latency_ms: float


@dataclass(frozen=True)
class VoiceSynthesisTrace:
    voice_session_id: uuid.UUID
    status: Literal["success", "failure", "interrupted"]
    tts_latency_ms: float


def log_turn_processing(trace: VoiceTurnProcessingTrace) -> None:
    logger.info(
        "voice_turn_processing",
        voice_session_id=str(trace.voice_session_id),
        status=trace.status,
        stt_latency_ms=round(trace.stt_latency_ms, 2),
        reply_latency_ms=(
            round(trace.reply_latency_ms, 2) if trace.reply_latency_ms is not None else None
        ),
        total_latency_ms=round(trace.total_latency_ms, 2),
    )


def log_synthesis(trace: VoiceSynthesisTrace) -> None:
    logger.info(
        "voice_synthesis",
        voice_session_id=str(trace.voice_session_id),
        status=trace.status,
        tts_latency_ms=round(trace.tts_latency_ms, 2),
    )
