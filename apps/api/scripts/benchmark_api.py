"""API performance benchmark (roadmap step 298) -- real wall-clock
latency for the core write/read paths a real user's first-time flow
exercises, measured against a REAL running server over real HTTP (not
TestClient's in-process shortcut), the same "run it for real" discipline
this project has followed throughout.

Runnable standalone: the server must already be running (`make
api-dev`), then `uv run python -m scripts.benchmark_api` from apps/api.
Same shape as voice/benchmark.py -- a real measurement tool, not a
CI-gated pass/fail assertion. These numbers are specific to whatever
machine runs them (this session: a single local Windows dev box, not
production hardware) -- there is no honest "must be under Nms"
threshold to assert without a real production-like benchmark
environment, so this reports numbers, it doesn't grade them.

Exercises a real first-time-user flow via genuine HTTP calls: signup ->
login -> create organization -> create workspace -> create knowledge
base -> keyword search against the (empty) knowledge base -> list
organizations. Each "write, unique per call" step gets its own fresh
throwaway org/user per iteration (can't replay a signup); each "read"
step reuses the first iteration's org across more repetitions, since
reads don't need fresh data to be a fair measurement.

Deliberately does NOT cover document upload/extraction/embedding or
dense/hybrid vector search -- those need a real OPENAI_API_KEY this
environment doesn't have (the same honest gap voice/benchmark.py and
eval/regression.py already established for the identical reason); a
fake/missing key would make either an outright failure or a
meaningless number, not a real measurement.
"""

import asyncio
import statistics
import sys
import time
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"
# Kept safely under signup's own real rate limit (5/hour per IP,
# rate_limit.py) -- discovered live running this script twice in a row
# during roadmap step 298: the first run's failed attempts (a benchmark
# bug, since fixed) still counted against the budget, since rate
# limiting happens before request-body validation. This script only
# gets one real budget per hour per machine; keep iterations well
# under 5 so a normal run doesn't self-lock out a same-hour rerun.
WRITE_ITERATIONS = 3
READ_ITERATIONS = 20


@dataclass
class EndpointStats:
    name: str
    latencies_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def record(self, latency_ms: float) -> None:
        self.latencies_ms.append(latency_ms)

    def record_error(self, detail: str) -> None:
        self.errors.append(detail)

    def summary(self) -> str:
        if not self.latencies_ms:
            detail = self.errors[0] if self.errors else "no runs"
            return f"{self.name}: 0/{len(self.errors)} succeeded -- {detail}"
        sorted_ms = sorted(self.latencies_ms)
        p50 = statistics.median(sorted_ms)
        p95 = sorted_ms[min(len(sorted_ms) - 1, int(len(sorted_ms) * 0.95))]
        mean = statistics.mean(sorted_ms)
        n_ok = len(self.latencies_ms)
        n_total = n_ok + len(self.errors)
        return (
            f"{self.name}: {n_ok}/{n_total} ok, "
            f"mean={mean:.1f}ms p50={p50:.1f}ms p95={p95:.1f}ms "
            f"min={sorted_ms[0]:.1f}ms max={sorted_ms[-1]:.1f}ms"
        )


async def _timed(coro: Coroutine[Any, Any, httpx.Response]) -> tuple[httpx.Response, float]:
    start = time.perf_counter()
    response = await coro
    return response, (time.perf_counter() - start) * 1000


async def run_benchmark() -> dict[str, EndpointStats]:
    stats: dict[str, EndpointStats] = {
        name: EndpointStats(name)
        for name in [
            "GET /health",
            "GET /ready",
            "POST /auth/signup",
            "POST /auth/login",
            "POST /organizations",
            "POST .../workspaces",
            "POST .../knowledge-bases",
            "GET /organizations (list)",
            "POST .../search/keyword (empty KB)",
        ]
    }

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        for _ in range(READ_ITERATIONS):
            resp, ms = await _timed(client.get("/health"))
            (stats["GET /health"].record(ms) if resp.status_code == 200 else None)
            resp, ms = await _timed(client.get("/ready"))
            (stats["GET /ready"].record(ms) if resp.status_code == 200 else None)

        first_org_context: dict[str, str] | None = None
        for i in range(WRITE_ITERATIONS):
            run_id = f"{uuid.uuid4().hex[:8]}"
            email = f"benchmark-{run_id}@example.com"

            resp, ms = await _timed(
                client.post(
                    "/auth/signup",
                    json={
                        "email": email,
                        "password": "BenchmarkPassword123!",
                        "full_name": "Benchmark User",
                    },
                )
            )
            if resp.status_code == 201:
                stats["POST /auth/signup"].record(ms)
            else:
                stats["POST /auth/signup"].record_error(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                continue

            resp, ms = await _timed(
                client.post(
                    "/auth/login", json={"email": email, "password": "BenchmarkPassword123!"}
                )
            )
            if resp.status_code != 200:
                stats["POST /auth/login"].record_error(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                continue
            stats["POST /auth/login"].record(ms)
            headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

            resp, ms = await _timed(
                client.post(
                    "/organizations",
                    json={"name": f"Benchmark Org {run_id}", "slug": f"benchmark-org-{run_id}"},
                    headers=headers,
                )
            )
            if resp.status_code != 201:
                stats["POST /organizations"].record_error(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                continue
            stats["POST /organizations"].record(ms)
            org_id = resp.json()["id"]

            resp, ms = await _timed(
                client.post(
                    f"/organizations/{org_id}/workspaces",
                    json={
                        "name": f"Benchmark Workspace {run_id}",
                        "slug": f"benchmark-ws-{run_id}",
                    },
                    headers=headers,
                )
            )
            if resp.status_code != 201:
                stats["POST .../workspaces"].record_error(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                continue
            stats["POST .../workspaces"].record(ms)
            workspace_id = resp.json()["id"]

            resp, ms = await _timed(
                client.post(
                    f"/organizations/{org_id}/workspaces/{workspace_id}/knowledge-bases",
                    json={"name": f"Benchmark KB {run_id}", "slug": f"benchmark-kb-{run_id}"},
                    headers=headers,
                )
            )
            if resp.status_code != 201:
                stats["POST .../knowledge-bases"].record_error(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
                continue
            stats["POST .../knowledge-bases"].record(ms)
            knowledge_base_id = resp.json()["id"]

            if i == 0:
                first_org_context = {
                    "org_id": org_id,
                    "workspace_id": workspace_id,
                    "kb_id": knowledge_base_id,
                    "Authorization": headers["Authorization"],
                }

        if first_org_context is not None:
            headers = {"Authorization": first_org_context["Authorization"]}
            org_id = first_org_context["org_id"]
            workspace_id = first_org_context["workspace_id"]
            kb_id = first_org_context["kb_id"]

            for _ in range(READ_ITERATIONS):
                resp, ms = await _timed(client.get("/organizations", headers=headers))
                if resp.status_code == 200:
                    stats["GET /organizations (list)"].record(ms)
                else:
                    stats["GET /organizations (list)"].record_error(f"HTTP {resp.status_code}")

                resp, ms = await _timed(
                    client.post(
                        f"/organizations/{org_id}/workspaces/{workspace_id}"
                        f"/knowledge-bases/{kb_id}/search/keyword",
                        json={"query": "test query", "top_k": 10},
                        headers=headers,
                    )
                )
                if resp.status_code == 200:
                    stats["POST .../search/keyword (empty KB)"].record(ms)
                else:
                    stats["POST .../search/keyword (empty KB)"].record_error(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )

    return stats


def main() -> int:
    print(
        f"Benchmarking {BASE_URL} -- {WRITE_ITERATIONS} write iterations, "
        f"{READ_ITERATIONS} read iterations"
    )
    print("(local dev machine numbers, not a production capacity claim)\n")
    try:
        stats = asyncio.run(run_benchmark())
    except httpx.ConnectError:
        print(f"Could not connect to {BASE_URL} -- is the server running (`make api-dev`)?")
        return 1

    for endpoint_stats in stats.values():
        print(endpoint_stats.summary())

    return 0


if __name__ == "__main__":
    sys.exit(main())
