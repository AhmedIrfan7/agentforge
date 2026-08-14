"""Tests for rerankers/lexical.py (roadmap step 125) -- LexicalReranker
is real, dependency-free logic (no API key, no model), so these are
plain unit tests against its actual token-overlap scoring, not fakes
or real-infra tests.
"""

import uuid

import pytest

from rerankers.base import RerankCandidate
from rerankers.lexical import LexicalReranker


@pytest.mark.anyio
async def test_candidate_covering_every_query_term_scores_highest() -> None:
    reranker = LexicalReranker()
    full_match = RerankCandidate(id=uuid.uuid4(), text="Our refund policy allows returns.")
    partial_match = RerankCandidate(id=uuid.uuid4(), text="Our shipping policy is simple.")
    no_match = RerankCandidate(id=uuid.uuid4(), text="Completely unrelated content here.")

    results = await reranker.rerank("refund policy", [no_match, partial_match, full_match])

    assert [r.id for r in results] == [full_match.id, partial_match.id, no_match.id]


@pytest.mark.anyio
async def test_score_is_the_fraction_of_query_tokens_present() -> None:
    reranker = LexicalReranker()
    candidate = RerankCandidate(id=uuid.uuid4(), text="refund only, nothing about the other word")

    results = await reranker.rerank("refund policy", [candidate])

    assert results[0].score == pytest.approx(0.5)


@pytest.mark.anyio
async def test_a_long_candidate_containing_every_query_term_still_scores_perfectly() -> None:
    """Recall-oriented by design -- extra unrelated words in a candidate
    should not dilute a perfect match, unlike a precision-style overlap
    metric would."""
    reranker = LexicalReranker()
    candidate = RerankCandidate(
        id=uuid.uuid4(),
        text=" ".join(["filler"] * 50) + " refund policy " + " ".join(["more filler"] * 50),
    )

    results = await reranker.rerank("refund policy", [candidate])

    assert results[0].score == pytest.approx(1.0)


@pytest.mark.anyio
async def test_empty_query_scores_every_candidate_zero_rather_than_dividing_by_zero() -> None:
    reranker = LexicalReranker()
    candidate = RerankCandidate(id=uuid.uuid4(), text="some real content")

    results = await reranker.rerank("", [candidate])

    assert results[0].score == 0.0


@pytest.mark.anyio
async def test_rerank_on_empty_candidates_returns_empty_list() -> None:
    reranker = LexicalReranker()
    results = await reranker.rerank("refund policy", [])
    assert results == []


@pytest.mark.anyio
async def test_matching_is_case_insensitive() -> None:
    reranker = LexicalReranker()
    candidate = RerankCandidate(id=uuid.uuid4(), text="REFUND POLICY in all caps")

    results = await reranker.rerank("refund policy", [candidate])

    assert results[0].score == pytest.approx(1.0)
