"""Streaming audio ingestion (roadmap step 221, Milestone 8) -- this
codebase's first real WebSocket endpoint. AGENTS.md's own "VOICE BOT
EXPERIENCE" section names "Streaming audio" outright; a plain HTTP
upload (like `routers/document.py`'s own file upload) can't carry a
real-time back-and-forth of many small audio chunks the way a live
voice call needs.

Deliberately narrow scope, matching this whole milestone's own
sequencing: this endpoint's ONLY job is real audio in, a real
transcript back out over the same connection -- it does NOT call the
orchestrator or generate an assistant reply (step 226, "wire Voice
Agent into orchestrator," is the explicit later step that wires a full
turn together), and it does NOT persist the transcript as a `Message`
row yet (step 226 is also what couples transcription with the real
`generate_assistant_reply` pipeline that does both persistence and
generation as one unit for text chat already -- writing only half of
that here now would leave a real, awkward partial state 226 would just
have to work around). No automatic "when did the user stop talking"
detection either -- silence detection (223) and voice-activity
detection (224) are explicit LATER steps; until they exist, the client
itself signals the end of a turn (an honest, real "push to talk" mode
many real voice products also support alongside auto-VAD, not a fake
stand-in for it).

A real, well-known FastAPI/Starlette limitation shapes this file's own
structure: `register_exception_handlers` (errors.py) only intercepts
exceptions raised while handling an HTTP request -- it does NOT apply
to WebSocket connections, and a `Depends()`-raised `AppError` inside a
websocket route does not get the same graceful JSON-response handling
`routers/public_conversation.py`'s own REST endpoints get for free.
This endpoint therefore does its own resolution/auth inline (reusing
the same real repository functions those REST dependencies already
call -- `get_public_assistant_by_id`, `origin_is_allowed`,
`decode_anonymous_session_token`, `VoiceSessionRepository` -- just not
wrapped in FastAPI's `Depends()`), and closes the socket with a real
WebSocket close code + a real reason string on any failure, instead of
trying to reuse REST's JSON error envelope over a connection that was
never an HTTP response to begin with.

Auth token travels as the FIRST message after the handshake, not a URL
query parameter -- an intentional choice over the other common real
pattern (`?token=...`): a token embedded in the connection URL is far
more likely to be captured somewhere it shouldn't be (browser history,
a reverse proxy's own access log, a devtools network panel a user
screenshots) than a value sent once inside the already-established,
encrypted (wss://) connection. The client's very first frame must be
JSON: `{"token": "<anonymous session token>", "mime_type": "audio/webm"}`
-- `mime_type` travels once per connection, not per chunk, since a
single recording session uses one consistent audio container the whole
time (matches `voice/whisper.py`'s own `mime_type` parameter, which
needs to know the real format to build a correctly-named multipart
upload).

After a successful auth handshake, the protocol is simple and
symmetric: BINARY frames are raw audio bytes, appended to an in-memory
per-connection buffer; the TEXT frame `{"type": "end_turn"}` finalizes
whatever's buffered, transcribes it via the real `WhisperSTTProvider`
(217) built at Milestone 8's own start, and sends the result back as
`{"type": "transcript", "text": ..., "language": ...}` (or
`{"type": "error", "message": ...}` on a real provider failure) --
then resets the buffer so the SAME connection can carry more than one
turn, matching `VoiceSession`'s own step-219 design (one session, one
open connection, potentially many real turns).

`MAX_AUDIO_BUFFER_BYTES` (20 MB, comfortably under OpenAI's own real
25 MiB Whisper request cap) is a real, deliberate safeguard this step
adds specifically because a WebSocket introduces a NEW resource-
exhaustion vector a bounded single HTTP upload never had: nothing
stops a client from holding the connection open and streaming audio
forever without ever sending `end_turn`. AGENTS.md's own "ABUSE
PREVENTION" section names exactly this class of risk
("prompt flooding"/"resource exhaustion"); exceeding the cap closes
the connection with WebSocket close code 1009 ("message too big"), the
closest standard code for this real (if here, cumulative-across-frames
rather than single-frame) condition.

As of step 223, a turn no longer strictly needs an explicit
`end_turn` message: `SILENCE_TIMEOUT_SECONDS` (1.5s) is a real,
honest, TIMING-based heuristic -- once real audio bytes have started
arriving for a turn, if no further audio frame arrives within that
window, the server treats it exactly like a real `end_turn` (same
`_finalize_turn` helper both paths now share). This is a deliberately
simple first layer, not real acoustic silence detection: nothing here
decodes the audio's actual content to check for real quiet vs. real
speech -- doing that would need a real audio codec/PCM-level analysis
this codebase doesn't have, which is exactly what "voice-activity
detection" (224, the very next step) is for. The explicit `end_turn`
message still works too (both paths call the same real finalize logic)
-- a real client can rely on either, or both together, matching 221's
own "auto detection alongside push-to-talk, not instead of it"
reasoning. The timeout only ever applies once the buffer is non-empty
-- an idle connection where the user simply hasn't started talking yet
uses a plain, un-timed `receive()`, so silence BEFORE a turn starts
never spuriously fires a transcription of nothing.

As of step 224, a second, CONTENT-aware layer complements step 223's
own pure-timing one: `_voice_activity_has_stopped` tracks the real
byte size of each binary chunk received during a turn and finalizes
early once several CONSECUTIVE recent chunks are all much smaller than
the turn's own peak chunk size so far. This closes a real gap 223
alone can't: a client that keeps sending frames on a fixed interval
regardless of whether the user is actually still talking (many real
`MediaRecorder` configurations do exactly this) would never trip
223's own inter-arrival-gap timer, since bytes never stop arriving --
but a real silent/background-noise period still compresses to
genuinely fewer bytes than active speech, even without decoding the
audio. This is the SAME real, well-known property that makes
Opus/webm's own variable-bitrate encoding what it is; leaning on it
needs zero new dependencies, unlike a real PCM-level/spectral VAD
(which would need an audio codec library or `ffmpeg` this codebase
doesn't otherwise depend on anywhere).

Honest about what this is and isn't: it is NOT real acoustic voice-
activity detection -- no decoding, no energy/spectral analysis of the
actual waveform, just a real, legitimate proxy on compressed chunk
size. It also can't distinguish "genuinely quiet speech" from "real
silence" as precisely as a decoded-PCM VAD model could, and the very
first chunk(s) of a container format like webm can be disproportionately
large purely from header/init-segment overhead, unrelated to whether
speech is present yet -- `VAD_MIN_CHUNKS_BEFORE_CHECK` (a real
minimum sample count before judging) and `VAD_QUIET_CHUNK_COUNT` (a
real run of CONSECUTIVE quiet chunks, not a single one) both exist
specifically to keep this heuristic from over-triggering on that kind
of noise. Runs INLINE, synchronously, right after each new chunk is
buffered -- no new timer, no new task, since it only needs to react to
chunks that have already arrived; 223's own timeout-based check still
independently covers the case where chunks stop arriving at all.

As of step 225, an in-flight `synthesize` no longer blocks the main
receive loop: it runs as a real, separate `asyncio.Task`
(`_stream_synthesis`), started and left running rather than awaited
directly, so the loop immediately goes back to `websocket.receive()`
while audio is still streaming out. This is what makes real barge-in
possible at all -- a single sequential `await` loop structurally
cannot notice a NEW incoming message while it's still in the middle of
sending a PREVIOUS one; two concurrent tasks sharing the same
WebSocket (one sending, one receiving) can. ANY new message the main
loop receives while a synthesis task is still running is treated as a
real interruption -- exactly how barge-in works in a real conversation
(a person starting to talk again IS the interruption signal; no
separate "stop" gesture is required first): the task is cancelled,
awaited so its cleanup actually completes before anything else
happens, and a real `{"type": "interrupted"}` message tells the client
to stop local playback of whatever it had already buffered. An
explicit `{"type": "interrupt"}` control message is also supported for
a client that wants to silence playback without necessarily having new
audio ready yet (e.g. a stop button) -- it rides the exact same
cancellation path (every message triggers the same check before
dispatch), and is a real no-op, not an error, if nothing was actually
playing.

As of step 222, the same connection also carries real synthesized
speech back to the client: `{"type": "synthesize", "text": "..."}`
calls the real `OpenAITTSProvider` (218) and streams its audio back as
a sequence of real BINARY frames (`AUDIO_STREAM_CHUNK_BYTES` each,
4 KB -- small enough that real client-side playback can start well
before the whole clip has arrived, the actual point of "streaming"
here, not an arbitrary number), terminated by a real
`{"type": "synthesis_done", "content_type": ...}` marker so the client
knows where one synthesis's audio ends (frames from a later synthesis,
or unrelated STT traffic on the same connection, could otherwise be
ambiguous). "Streaming" is real transport chunking of one already-
fully-synthesized buffer, not real token-level incremental TTS
generation -- OpenAI's own TTS API returns one complete audio response,
not a token stream, the same honest "real transport, not real
generation-level streaming" distinction `docs/ARCHITECTURE.md`'s own
Conversation Engine section already draws for SSE text streaming.

As of step 226, a finished turn is finally a REAL conversation turn,
not just a transcript echoed back: `_finalize_turn` now calls the
exact same `message_processing.py:generate_assistant_reply` pipeline
text chat already uses -- the real orchestrator call, real citation
building, and persisting BOTH the user's and the assistant's `Message`
rows under this voice session's own `conversation_id` (step 219's own
"a voice session is a real conversations.id FK, not a parallel
transcript system" design finally has a real writer). The reply text
comes back as `{"type": "reply", "text": ..., "citations": [...]}`
(the same citation shape `CitationRead`/`citation_json` already
produce for text chat, sent as real, immediate on-screen/caption text
a client can render right away), then the SAME `_stream_synthesis`
mechanism (222/225) speaks it -- so a real voice turn now goes
audio-in -> real transcript -> real orchestrator reply -> real speech
back out, entirely through infrastructure this milestone already
built and tested piece by piece, not new machinery invented here.

A real empty/near-silent transcript (Whisper can legitimately return
whitespace-only text for audio that still passed VAD's own crude
size-based check) skips generation entirely -- the transcript is still
sent honestly, but there's nothing meaningful to route through the
orchestrator, and doing so anyway would be a wasted real LLM-adjacent
call for a message with no content. The SAME per-tenant rate limit
`routers/public_conversation.py`'s own anonymous message-send already
enforces (`check_rate_limit`, keyed by `tenant_id`, shared budget
across every real door into `orchestrator.handle()`) applies here too,
now that this endpoint finally triggers that real cost -- checked right
before calling `generate_assistant_reply`, not on every audio chunk,
since a chunk isn't a turn.

`_authenticate` now returns a small `_AuthenticatedSession` bundle
(`mime_type`/`tenant_id`/`assistant_id`/`conversation_id`/
`voice_session_id`) instead of just `mime_type` -- plain values, not
the `Assistant`/`Conversation` ORM objects themselves, since those
would be bound to the auth-time session and unsafe to touch once it
closes (the exact `Message`/`Conversation` attribute-expiry class of
bug steps 189/193 already found live in this codebase); `_finalize_
turn` opens its own fresh session and re-fetches both by id when it
actually needs them.

As of step 227, `voice/tracing.py` gives every real turn a real
latency trace -- `log_turn_processing` (STT + reply-generation
latency, the synchronous time a caller waits in silence) from
`_finalize_turn`, and `log_synthesis` (real TTS provider latency,
including a genuine `status="interrupted"` outcome for a real
barge-in cancellation) from `_stream_synthesis`. See that module's own
docstring for why these are two separate events rather than one.
"""

import asyncio
import contextlib
import json
import time
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth.jwt import TokenError, decode_anonymous_session_token
from db import get_session, set_tenant_context
from errors import TooManyRequestsError
from message_processing import generate_assistant_reply
from rate_limit import MESSAGE_SEND_RATE_LIMIT, check_rate_limit
from repositories.assistant import AssistantRepository, get_public_assistant_by_id
from repositories.conversation import ConversationRepository
from repositories.security_settings import SecuritySettingsRepository, origin_is_allowed
from repositories.voice_session import VoiceSessionRepository
from voice.base import SpeechProviderError
from voice.openai_tts import OpenAITTSProvider
from voice.tracing import (
    VoiceSynthesisTrace,
    VoiceTurnProcessingTrace,
    log_synthesis,
    log_turn_processing,
)
from voice.whisper import WhisperSTTProvider

router = APIRouter(prefix="/public/assistants/{assistant_id}/voice-sessions", tags=["public-voice"])

MAX_AUDIO_BUFFER_BYTES = 20 * 1024 * 1024
AUDIO_STREAM_CHUNK_BYTES = 4096
SILENCE_TIMEOUT_SECONDS = 1.5
VAD_MIN_CHUNKS_BEFORE_CHECK = 4
VAD_QUIET_CHUNK_COUNT = 3
VAD_QUIET_THRESHOLD_RATIO = 0.3

_stt_provider = WhisperSTTProvider()
_tts_provider = OpenAITTSProvider()


def _voice_activity_has_stopped(chunk_sizes: list[int]) -> bool:
    """Real content-size heuristic (224) -- see this module's own
    docstring for the full reasoning. Pure and synchronous on purpose:
    no I/O, easy to unit-test in isolation from the websocket/async
    machinery around it."""
    if len(chunk_sizes) < VAD_MIN_CHUNKS_BEFORE_CHECK:
        return False
    peak = max(chunk_sizes)
    if peak == 0:
        return False
    recent = chunk_sizes[-VAD_QUIET_CHUNK_COUNT:]
    return all(size < peak * VAD_QUIET_THRESHOLD_RATIO for size in recent)


@dataclass(frozen=True)
class _AuthenticatedSession:
    mime_type: str
    tenant_id: uuid.UUID
    assistant_id: uuid.UUID
    conversation_id: uuid.UUID
    voice_session_id: uuid.UUID


async def _authenticate(
    websocket: WebSocket, assistant_id: uuid.UUID, voice_session_id: uuid.UUID
) -> _AuthenticatedSession | None:
    """Validates the first message, the assistant, and the voice
    session. Returns a real `_AuthenticatedSession` bundle on success;
    sends a real `{"type": "error", ...}` message and closes the
    socket (returning None) on any failure -- every failure path
    closes with 1008 (Policy Violation), the standard WebSocket code
    for "you violated this endpoint's own protocol/authorization
    rules," matching how `errors.UnauthorizedError`/`NotFoundError`
    would 401/404 the equivalent REST request.
    """
    first_message = await websocket.receive()
    if first_message["type"] == "websocket.disconnect":
        return None

    raw_text = first_message.get("text")
    if raw_text is None:
        await websocket.send_json({"type": "error", "message": "First message must be JSON text."})
        await websocket.close(code=1008, reason="Invalid first message.")
        return None

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "message": "First message must be valid JSON."})
        await websocket.close(code=1008, reason="Invalid first message.")
        return None

    token = payload.get("token")
    mime_type = payload.get("mime_type")
    if not isinstance(token, str) or not token or not isinstance(mime_type, str) or not mime_type:
        await websocket.send_json(
            {"type": "error", "message": "First message must include token and mime_type."}
        )
        await websocket.close(code=1008, reason="Missing token or mime_type.")
        return None

    try:
        token_conversation_id = decode_anonymous_session_token(token)
    except TokenError:
        await websocket.send_json({"type": "error", "message": "Invalid or expired session."})
        await websocket.close(code=1008, reason="Invalid session token.")
        return None

    async with get_session() as session:
        assistant = await get_public_assistant_by_id(session, assistant_id)
        if assistant is None:
            await websocket.send_json({"type": "error", "message": "Assistant not found."})
            await websocket.close(code=1008, reason="Assistant not found.")
            return None
        await set_tenant_context(session, assistant.tenant_id)

        security_settings = await SecuritySettingsRepository(
            session, assistant.tenant_id
        ).get_singleton()
        origin = websocket.headers.get("origin")
        allowed_domains = security_settings.allowed_domains if security_settings else []
        if allowed_domains and origin and not origin_is_allowed(origin, allowed_domains):
            await websocket.send_json(
                {"type": "error", "message": "This assistant is not permitted on this domain."}
            )
            await websocket.close(code=1008, reason="Origin not allowed.")
            return None

        voice_session = await VoiceSessionRepository(session, assistant.tenant_id).get(
            voice_session_id
        )
        if (
            voice_session is None
            or voice_session.conversation_id != token_conversation_id
            or voice_session.ended_at is not None
        ):
            await websocket.send_json({"type": "error", "message": "Voice session not found."})
            await websocket.close(code=1008, reason="Voice session not found.")
            return None

    return _AuthenticatedSession(
        mime_type=mime_type,
        tenant_id=assistant.tenant_id,
        assistant_id=assistant.id,
        conversation_id=token_conversation_id,
        voice_session_id=voice_session_id,
    )


async def _stream_synthesis(websocket: WebSocket, text: str, voice_session_id: uuid.UUID) -> None:
    """Synthesizes `text` and streams it back as chunked binary frames
    (222) -- run as a standalone `asyncio.Task` (225) rather than
    awaited inline, so a real barge-in can cancel it mid-flight,
    including while the provider call itself is still in progress, not
    just between already-queued chunks. The outer `CancelledError`
    handler (227) is what lets a real interruption still produce a real
    latency trace -- logged as `status="interrupted"`, not silently
    lost, then re-raised unchanged so real cancellation semantics for
    the caller (`_interrupt_active_synthesis`) are untouched."""
    start = time.perf_counter()
    try:
        try:
            synthesis = await _tts_provider.synthesize(text)
        except SpeechProviderError:
            log_synthesis(
                VoiceSynthesisTrace(
                    voice_session_id=voice_session_id,
                    status="failure",
                    tts_latency_ms=(time.perf_counter() - start) * 1000,
                )
            )
            await websocket.send_json(
                {"type": "error", "message": "Speech synthesis failed. Please try again."}
            )
            return
        log_synthesis(
            VoiceSynthesisTrace(
                voice_session_id=voice_session_id,
                status="success",
                tts_latency_ms=(time.perf_counter() - start) * 1000,
            )
        )
        for offset in range(0, len(synthesis.audio), AUDIO_STREAM_CHUNK_BYTES):
            await websocket.send_bytes(synthesis.audio[offset : offset + AUDIO_STREAM_CHUNK_BYTES])
        await websocket.send_json(
            {"type": "synthesis_done", "content_type": synthesis.content_type}
        )
    except asyncio.CancelledError:
        log_synthesis(
            VoiceSynthesisTrace(
                voice_session_id=voice_session_id,
                status="interrupted",
                tts_latency_ms=(time.perf_counter() - start) * 1000,
            )
        )
        raise


async def _interrupt_active_synthesis(
    websocket: WebSocket, synthesis_task: asyncio.Task[None] | None
) -> None:
    """Cancels a still-running synthesis task and acknowledges the
    interruption -- the one real "stop speaking, something new just
    happened" action (225), shared by every real trigger: a new client
    message, or a turn finalizing automatically via the silence-timeout
    path, which receives no new message at all and so can't rely on the
    main loop's own per-message interruption check. A no-op, correctly
    silent, if nothing was actually playing."""
    if synthesis_task is None or synthesis_task.done():
        return
    synthesis_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await synthesis_task
    await websocket.send_json({"type": "interrupted"})


async def _finalize_turn(
    websocket: WebSocket, buffer: bytearray, chunk_sizes: list[int], auth: _AuthenticatedSession
) -> asyncio.Task[None] | None:
    """Transcribes whatever's buffered, generates a real assistant
    reply through the exact same `generate_assistant_reply` pipeline
    text chat uses, and starts speaking it back -- the one real "a turn
    just ended" action, shared by the explicit `end_turn` message, the
    silence-timeout path (223), and the voice-activity path (224) so
    none of the three duplicates the others' error handling or per-turn
    state reset. `chunk_sizes` resets alongside `buffer` -- both
    describe the SAME now-finished turn. Returns the new synthesis
    task (or None on any failure/empty turn) so the caller tracks it
    the same way an explicit `synthesize` request already does.

    Also where step 227's own `voice_turn_processing` trace is logged
    -- `stt_latency_ms`/`reply_latency_ms` cover exactly the two real,
    synchronous stages a caller waits through before hearing anything
    back; `total_latency_ms` is their real sum plus whatever else ran
    between them (the transcript send, the rate-limit check), the
    single number that answers "how long did the user actually wait in
    silence" (AGENTS.md's own "Fast response time")."""
    turn_start = time.perf_counter()
    try:
        stt_start = time.perf_counter()
        result = await _stt_provider.transcribe(bytes(buffer), mime_type=auth.mime_type)
        stt_latency_ms = (time.perf_counter() - stt_start) * 1000
    except SpeechProviderError:
        log_turn_processing(
            VoiceTurnProcessingTrace(
                voice_session_id=auth.voice_session_id,
                status="failure",
                stt_latency_ms=(time.perf_counter() - turn_start) * 1000,
                reply_latency_ms=None,
                total_latency_ms=(time.perf_counter() - turn_start) * 1000,
            )
        )
        await websocket.send_json(
            {"type": "error", "message": "Transcription failed. Please try again."}
        )
        return None
    finally:
        buffer.clear()
        chunk_sizes.clear()

    await websocket.send_json(
        {"type": "transcript", "text": result.text, "language": result.language}
    )

    if not result.text.strip():
        log_turn_processing(
            VoiceTurnProcessingTrace(
                voice_session_id=auth.voice_session_id,
                status="success",
                stt_latency_ms=stt_latency_ms,
                reply_latency_ms=None,
                total_latency_ms=(time.perf_counter() - turn_start) * 1000,
            )
        )
        return None

    try:
        await check_rate_limit(
            f"message_send:{auth.tenant_id}", limit=MESSAGE_SEND_RATE_LIMIT, window_seconds=60
        )
    except TooManyRequestsError:
        await websocket.send_json(
            {"type": "error", "message": "Too many messages. Please try again shortly."}
        )
        return None

    reply_start = time.perf_counter()
    async with get_session() as session:
        await set_tenant_context(session, auth.tenant_id)
        assistant = await AssistantRepository(session, auth.tenant_id).get(auth.assistant_id)
        conversation = await ConversationRepository(session, auth.tenant_id).get(
            auth.conversation_id
        )
        if assistant is None or conversation is None:
            await websocket.send_json(
                {"type": "error", "message": "This voice session is no longer available."}
            )
            return None
        try:
            assistant_message = await generate_assistant_reply(
                session, auth.tenant_id, assistant, conversation, result.text
            )
        except Exception:
            await session.rollback()
            raise
        await session.commit()
        reply_text = assistant_message.content
        citations = assistant_message.citations
    reply_latency_ms = (time.perf_counter() - reply_start) * 1000

    log_turn_processing(
        VoiceTurnProcessingTrace(
            voice_session_id=auth.voice_session_id,
            status="success",
            stt_latency_ms=stt_latency_ms,
            reply_latency_ms=reply_latency_ms,
            total_latency_ms=(time.perf_counter() - turn_start) * 1000,
        )
    )

    await websocket.send_json({"type": "reply", "text": reply_text, "citations": citations})
    return asyncio.create_task(_stream_synthesis(websocket, reply_text, auth.voice_session_id))


@router.websocket("/{voice_session_id}/audio")
async def stream_voice_session_audio(
    websocket: WebSocket, assistant_id: uuid.UUID, voice_session_id: uuid.UUID
) -> None:
    await websocket.accept()

    auth = await _authenticate(websocket, assistant_id, voice_session_id)
    if auth is None:
        return

    await websocket.send_json({"type": "ready"})

    buffer = bytearray()
    chunk_sizes: list[int] = []
    synthesis_task: asyncio.Task[None] | None = None
    try:
        while True:
            if buffer:
                # A turn is in progress -- only now does silence carry
                # real meaning (see this module's own step-223 docstring
                # for why an idle, not-yet-started connection must never
                # time out this way).
                try:
                    message = await asyncio.wait_for(
                        websocket.receive(), timeout=SILENCE_TIMEOUT_SECONDS
                    )
                except TimeoutError:
                    # The timeout fired instead of a real message, so
                    # the main interruption-check below never runs for
                    # this iteration -- a still-active synthesis (e.g.
                    # started just before this turn's own silence
                    # window closed) needs the same real interruption
                    # here, not just when a new message actually arrives.
                    await _interrupt_active_synthesis(websocket, synthesis_task)
                    synthesis_task = await _finalize_turn(websocket, buffer, chunk_sizes, auth)
                    continue
            else:
                message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                if synthesis_task is not None and not synthesis_task.done():
                    synthesis_task.cancel()
                return

            # Real barge-in (225): ANY new message while a synthesis is
            # still streaming out is treated as the user interrupting
            # it -- the same way a person starting to talk again IS the
            # interruption in a real conversation, no separate "stop"
            # gesture required first.
            await _interrupt_active_synthesis(websocket, synthesis_task)
            synthesis_task = None

            if "bytes" in message and message["bytes"] is not None:
                chunk = message["bytes"]
                buffer.extend(chunk)
                if len(buffer) > MAX_AUDIO_BUFFER_BYTES:
                    await websocket.send_json(
                        {"type": "error", "message": "Too much audio buffered without end_turn."}
                    )
                    await websocket.close(code=1009, reason="Audio buffer limit exceeded.")
                    return
                chunk_sizes.append(len(chunk))
                if _voice_activity_has_stopped(chunk_sizes):
                    synthesis_task = await _finalize_turn(websocket, buffer, chunk_sizes, auth)
                continue

            if "text" not in message or message["text"] is None:
                continue

            try:
                control = json.loads(message["text"])
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON message."})
                continue

            control_type = control.get("type")

            if control_type == "end_turn":
                if not buffer:
                    await websocket.send_json(
                        {"type": "error", "message": "No audio received before end_turn."}
                    )
                    continue
                synthesis_task = await _finalize_turn(websocket, buffer, chunk_sizes, auth)
                continue

            if control_type == "synthesize":
                text = control.get("text")
                if not isinstance(text, str) or not text:
                    await websocket.send_json(
                        {"type": "error", "message": "synthesize requires non-empty text."}
                    )
                    continue
                synthesis_task = asyncio.create_task(
                    _stream_synthesis(websocket, text, auth.voice_session_id)
                )
                continue

            if control_type == "interrupt":
                # A real no-op, not an error, if nothing was actually
                # playing -- the interruption-check above already
                # cancelled and acknowledged any in-flight synthesis
                # before this dispatch ever runs.
                continue

            await websocket.send_json({"type": "error", "message": "Unknown message type."})
    except WebSocketDisconnect:
        return
    finally:
        # A synthesis task's own send calls can outlive an already-
        # closed connection (e.g. the client disconnects mid-stream) --
        # cancel it rather than leaving an orphaned task with an
        # unretrieved exception.
        if synthesis_task is not None and not synthesis_task.done():
            synthesis_task.cancel()
