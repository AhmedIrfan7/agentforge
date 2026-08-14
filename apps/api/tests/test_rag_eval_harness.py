"""Tests for eval/harness.py (roadmap step 128) -- this IS the
harness's own live verification (no HTTP endpoint exists to wire it
into, same "no live-server verification needed" position as steps
118/125/126/127): seeds the real fixture corpus into real Postgres and
scores real `ChunkRepository.search_by_keyword` against it -- keyword
search works for real in every environment, including one with no
OPENAI_API_KEY (the same documented gap dense search has had since
step 107), so it's the mechanism this test can honestly run for real
rather than needing a fake embedding provider.
"""

import uuid

import pytest

from db import get_session, set_tenant_context
from eval.fixtures import RETRIEVAL_FIXTURES
from eval.harness import run_eval, seed_fixture_set
from repositories.chunk import ChunkRepository


@pytest.mark.anyio
async def test_keyword_search_scores_perfectly_on_the_well_separated_fixture_set() -> None:
    """The fixture corpus (eval/fixtures.py) was deliberately built with
    distinct enough topics that a real retriever should find the exact
    right document for every query -- this is the harness proving
    itself against a mechanism already independently trusted
    (test_chunk_repository_keyword_search.py), not the other way
    around."""
    seeded = await seed_fixture_set(RETRIEVAL_FIXTURES, slug_prefix="rag-eval-kw")

    async def search(query: str) -> list[uuid.UUID]:
        async with get_session() as session:
            await set_tenant_context(session, seeded.tenant_id)
            repo = ChunkRepository(session, seeded.tenant_id)
            results = await repo.search_by_keyword(seeded.knowledge_base_id, query, top_k=5)
            return [r.document_id for r in results]

    report = await run_eval(RETRIEVAL_FIXTURES, seeded, search, k=5)

    assert report.mean_precision == pytest.approx(1.0)
    assert report.mean_recall == pytest.approx(1.0)
    assert len(report.case_results) == len(RETRIEVAL_FIXTURES.cases)


@pytest.mark.anyio
async def test_a_search_that_finds_nothing_scores_zero_on_both_metrics() -> None:
    """Proves the harness doesn't silently pass when retrieval fails --
    a search stub that never returns anything relevant should score 0,
    not be hidden by an averaging bug."""
    seeded = await seed_fixture_set(RETRIEVAL_FIXTURES, slug_prefix="rag-eval-empty")

    async def search(_query: str) -> list[uuid.UUID]:
        return []

    report = await run_eval(RETRIEVAL_FIXTURES, seeded, search, k=5)

    assert report.mean_precision == 0.0
    assert report.mean_recall == 0.0


@pytest.mark.anyio
async def test_seeding_creates_one_real_document_per_fixture_document() -> None:
    seeded = await seed_fixture_set(RETRIEVAL_FIXTURES, slug_prefix="rag-eval-seed")

    assert len(seeded.key_to_document_id) == len(RETRIEVAL_FIXTURES.documents)
    assert set(seeded.key_to_document_id.keys()) == {d.key for d in RETRIEVAL_FIXTURES.documents}
