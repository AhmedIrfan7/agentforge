"""Retrieval regression script (roadmap step 135) -- runs eval/
harness.py's real precision/recall evaluation against eval/fixtures.py's
benchmark corpus (step 128, reused rather than duplicated: it's already
a real, labeled, well-separated dataset -- building a second, near-
identical one for "benchmarking" would be pure duplication with no
real additional value) and fails if either metric drops below a fixed
threshold, guarding against a future code change silently degrading
retrieval quality. Runnable standalone (`python -m eval.regression`,
prints a per-case report and exits nonzero on failure) or from pytest
(tests/test_retrieval_regression.py) -- one real function either way,
not two separate implementations to keep in sync.

Scoped to keyword search only for its real, meaningful pass/fail
threshold: this is the one retrieval mechanism that works for real in
every environment, including one with no OPENAI_API_KEY (the same
documented gap dense/hybrid have had since step 107) -- a fake
embedding provider would only prove fake-vector arithmetic still
works, not catch a real regression in dense retrieval quality, so
asserting a threshold there would be dishonest, not a genuine guard.

MIN_PRECISION/MIN_RECALL are both 1.0, not an arbitrary lower bar: the
benchmark corpus was deliberately built (step 128) so every query has
exactly one, unambiguous correct answer -- a real drop below 1.0 on
this specific, constructed corpus means something genuinely broke, not
noise a looser threshold would need to absorb.
"""

import asyncio
import sys
import uuid

from db import get_session, set_tenant_context
from eval.fixtures import RETRIEVAL_FIXTURES
from eval.harness import EvalReport, run_eval, seed_fixture_set
from repositories.chunk import ChunkRepository

MIN_PRECISION = 1.0
MIN_RECALL = 1.0


async def _search_by_keyword(
    tenant_id: uuid.UUID, knowledge_base_id: uuid.UUID, query: str
) -> list[uuid.UUID]:
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = ChunkRepository(session, tenant_id)
        results = await repo.search_by_keyword(knowledge_base_id, query, top_k=5)
        return [r.document_id for r in results]


async def run_regression() -> EvalReport:
    seeded = await seed_fixture_set(RETRIEVAL_FIXTURES, slug_prefix="retrieval-regression")

    async def search(query: str) -> list[uuid.UUID]:
        return await _search_by_keyword(seeded.tenant_id, seeded.knowledge_base_id, query)

    return await run_eval(RETRIEVAL_FIXTURES, seeded, search, k=5)


def _print_report(report: EvalReport) -> None:
    print(f"mean_precision={report.mean_precision:.3f} (threshold {MIN_PRECISION})")
    print(f"mean_recall={report.mean_recall:.3f} (threshold {MIN_RECALL})")
    for case in report.case_results:
        print(f"  {case.query!r}: precision={case.precision:.3f} recall={case.recall:.3f}")


def main() -> int:
    report = asyncio.run(run_regression())
    _print_report(report)
    passed = report.mean_precision >= MIN_PRECISION and report.mean_recall >= MIN_RECALL
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
