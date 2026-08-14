"""Tests for rerankers/base.py (roadmap step 125).

Same reasoning test_embedding_provider.py/test_vectorstore_base.py
already established for this project's other interface-first steps:
proves a real class implementing exactly the documented Protocol shape
works the way the interface promises.
"""

import uuid
from dataclasses import dataclass, field

import pytest

from rerankers.base import RerankCandidate, RerankerProvider, RerankResult


@dataclass
class _FakeReranker:
    """A real implementation of RerankerProvider -- not a mock of one --
    same reasoning _FakeVectorStore/_FakeEmbeddingProvider already
    established for this project's other provider interfaces. Scores by
    how many times the query string appears as a literal substring of
    each candidate's text, real if trivial."""

    name: str = "fake"
    _scores_by_id: dict[uuid.UUID, float] = field(default_factory=dict)

    async def rerank(self, query: str, candidates: list[RerankCandidate]) -> list[RerankResult]:
        scored = [
            RerankResult(id=c.id, score=float(c.text.lower().count(query.lower())))
            for c in candidates
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored


def test_fake_reranker_satisfies_the_protocol_structurally() -> None:
    reranker: RerankerProvider = _FakeReranker(name="fake")
    assert reranker.name == "fake"


@pytest.mark.anyio
async def test_rerank_returns_one_result_per_candidate() -> None:
    reranker = _FakeReranker()
    candidates = [
        RerankCandidate(id=uuid.uuid4(), text="refund policy details"),
        RerankCandidate(id=uuid.uuid4(), text="unrelated shipping info"),
    ]

    results = await reranker.rerank("refund", candidates)

    assert len(results) == 2
    assert {r.id for r in results} == {c.id for c in candidates}


@pytest.mark.anyio
async def test_rerank_on_empty_candidates_returns_empty_list() -> None:
    reranker = _FakeReranker()
    results = await reranker.rerank("refund", [])
    assert results == []
