"""Voice quality/latency benchmark script (roadmap step 231) -- a real
TTS->STT round trip over a small fixture set of representative texts,
measuring both providers' real wall-clock latency AND a real quality
signal: since each case's input text is known ground truth, the
benchmark can score how closely Whisper's own transcription of the
synthesized audio matches what was actually said, not just whether the
calls succeeded. Runnable standalone (`python -m voice.benchmark`,
prints a per-case report) -- same "one real function, runnable either
as a script or imported" shape `eval/regression.py` (135) already
established for the RAG side.

Deliberately no DB/tenant context at all, unlike `eval/harness.py`'s
own fixture seeding -- provider latency is a property of the provider
call itself, not of anything stored in Postgres, so seeding a fixture
corpus into a real org/workspace/kb the way retrieval benchmarking
needs to would be pure unnecessary machinery here.

Deliberately no CI-gating pytest counterpart, unlike `eval/regression.
py`'s dual script+pytest shape -- that script could scope itself to
keyword search specifically BECAUSE keyword search "works for real in
every environment, including one with no OPENAI_API_KEY" (its own
docstring). Every voice provider in this codebase is OpenAI-backed;
there is no environment-independent voice path to assert a threshold
against, so a hard pass/fail gate here would be asserting against
infrastructure (a real API key) this repo's own CI/local dev honestly
doesn't have, the same reasoning that already kept dense/hybrid
retrieval out of that regression gate. `main()` always exits 0 once a
report is produced, even a report showing zero successful calls --
that IS the honest, correct measurement of an environment with no
configured key, not a script failure.

Text-similarity uses `difflib.SequenceMatcher` (stdlib, zero new
dependency) rather than a real WER library -- a real word-error-rate
metric would need its own new dependency for a single benchmark
script; a simple normalized character-level ratio is honest about
being an approximation, not a claimed industry-standard WER score.
"""

import asyncio
import sys
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import mean

from voice.base import SpeechProviderError
from voice.openai_tts import OpenAITTSProvider
from voice.whisper import WhisperSTTProvider

FIXTURE_TEXTS = [
    "Yes.",
    "Our refund policy allows returns within thirty days of purchase.",
    (
        "To reset your password, open the account settings page, select "
        "security, and follow the link we email you. The link expires "
        "after one hour for your protection."
    ),
]


@dataclass(frozen=True)
class BenchmarkCaseResult:
    text: str
    tts_status: str  # "success" | "failure"
    tts_latency_ms: float | None
    stt_status: str  # "success" | "failure" | "skipped"
    stt_latency_ms: float | None
    transcribed_text: str | None
    text_similarity: float | None


@dataclass(frozen=True)
class BenchmarkReport:
    case_results: list[BenchmarkCaseResult]
    tts_success_rate: float
    stt_success_rate: float
    mean_tts_latency_ms: float | None
    mean_stt_latency_ms: float | None
    mean_text_similarity: float | None


def _text_similarity(original: str, transcribed: str) -> float:
    return SequenceMatcher(None, original.strip().lower(), transcribed.strip().lower()).ratio()


async def _run_case(text: str) -> BenchmarkCaseResult:
    tts_provider = OpenAITTSProvider()
    start = time.perf_counter()
    try:
        synthesis = await tts_provider.synthesize(text)
    except SpeechProviderError:
        return BenchmarkCaseResult(
            text=text,
            tts_status="failure",
            tts_latency_ms=(time.perf_counter() - start) * 1000,
            stt_status="skipped",
            stt_latency_ms=None,
            transcribed_text=None,
            text_similarity=None,
        )
    tts_latency_ms = (time.perf_counter() - start) * 1000

    stt_provider = WhisperSTTProvider()
    start = time.perf_counter()
    try:
        transcription = await stt_provider.transcribe(
            synthesis.audio, mime_type=synthesis.content_type
        )
    except SpeechProviderError:
        return BenchmarkCaseResult(
            text=text,
            tts_status="success",
            tts_latency_ms=tts_latency_ms,
            stt_status="failure",
            stt_latency_ms=(time.perf_counter() - start) * 1000,
            transcribed_text=None,
            text_similarity=None,
        )
    stt_latency_ms = (time.perf_counter() - start) * 1000

    return BenchmarkCaseResult(
        text=text,
        tts_status="success",
        tts_latency_ms=tts_latency_ms,
        stt_status="success",
        stt_latency_ms=stt_latency_ms,
        transcribed_text=transcription.text,
        text_similarity=_text_similarity(text, transcription.text),
    )


async def run_benchmark() -> BenchmarkReport:
    case_results = [await _run_case(text) for text in FIXTURE_TEXTS]

    tts_latencies = [
        c.tts_latency_ms
        for c in case_results
        if c.tts_status == "success" and c.tts_latency_ms is not None
    ]
    stt_latencies = [
        c.stt_latency_ms
        for c in case_results
        if c.stt_status == "success" and c.stt_latency_ms is not None
    ]
    similarities = [c.text_similarity for c in case_results if c.text_similarity is not None]

    return BenchmarkReport(
        case_results=case_results,
        tts_success_rate=sum(c.tts_status == "success" for c in case_results) / len(case_results),
        stt_success_rate=sum(c.stt_status == "success" for c in case_results) / len(case_results),
        mean_tts_latency_ms=mean(tts_latencies) if tts_latencies else None,
        mean_stt_latency_ms=mean(stt_latencies) if stt_latencies else None,
        mean_text_similarity=mean(similarities) if similarities else None,
    )


def _print_report(report: BenchmarkReport) -> None:
    print(f"tts_success_rate={report.tts_success_rate:.0%}")
    print(f"stt_success_rate={report.stt_success_rate:.0%}")
    print(
        "mean_tts_latency_ms="
        + (f"{report.mean_tts_latency_ms:.1f}" if report.mean_tts_latency_ms is not None else "n/a")
    )
    print(
        "mean_stt_latency_ms="
        + (f"{report.mean_stt_latency_ms:.1f}" if report.mean_stt_latency_ms is not None else "n/a")
    )
    print(
        "mean_text_similarity="
        + (
            f"{report.mean_text_similarity:.3f}"
            if report.mean_text_similarity is not None
            else "n/a"
        )
    )
    for case in report.case_results:
        tts_ms = f"{case.tts_latency_ms:.1f}ms" if case.tts_latency_ms is not None else "n/a"
        stt_ms = f"{case.stt_latency_ms:.1f}ms" if case.stt_latency_ms is not None else "n/a"
        print(f"  {case.text!r}")
        print(f"    tts={case.tts_status} ({tts_ms})")
        print(f"    stt={case.stt_status} ({stt_ms})")
        if case.transcribed_text is not None:
            print(f"    transcribed={case.transcribed_text!r} similarity={case.text_similarity}")
    if report.tts_success_rate == 0.0:
        print(
            "\nNo successful TTS calls -- this environment likely has no real "
            "OPENAI_API_KEY configured. This is an honest, expected result "
            "locally/in CI, not a script bug."
        )


def main() -> int:
    report = asyncio.run(run_benchmark())
    _print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
