"""Tests for context_builder.py (roadmap step 126) -- pure function
tests, no DB/HTTP needed (same reasoning test_retrieval_fusion.py
already established for its own pure algorithmic module).
"""

import uuid

from context_builder import ContextCandidate, build_context, count_tokens


def _candidate(
    *, text: str, document_id: uuid.UUID | None = None, score: float = 1.0
) -> ContextCandidate:
    return ContextCandidate(
        id=uuid.uuid4(), document_id=document_id or uuid.uuid4(), text=text, score=score
    )


def test_count_tokens_matches_a_real_known_encoding() -> None:
    # A single common English word tokenizes to exactly one token under
    # cl100k_base -- a real, checkable fact about the real encoding,
    # not an arbitrary assertion.
    assert count_tokens("hello") == 1


def test_count_tokens_of_empty_string_is_zero() -> None:
    assert count_tokens("") == 0


def test_dedupe_keeps_only_the_first_occurrence_of_identical_text() -> None:
    document_id = uuid.uuid4()
    first = _candidate(text="Our refund policy allows returns.", document_id=document_id)
    duplicate = _candidate(text="Our refund policy allows returns.", document_id=document_id)

    result = build_context([first, duplicate], max_tokens=1000)

    assert [c.id for c in result] == [first.id]


def test_dedupe_is_case_and_whitespace_insensitive() -> None:
    first = _candidate(text="Refund policy details.")
    duplicate = _candidate(text="  REFUND POLICY DETAILS.  ")

    result = build_context([first, duplicate], max_tokens=1000)

    assert len(result) == 1
    assert result[0].id == first.id


def test_distinct_text_is_never_deduped() -> None:
    a = _candidate(text="Refund policy details.")
    b = _candidate(text="Shipping policy details.")

    result = build_context([a, b], max_tokens=1000)

    assert {c.id for c in result} == {a.id, b.id}


def test_chunks_from_the_same_document_are_grouped_adjacent() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    a1 = _candidate(text="doc a chunk one", document_id=doc_a)
    b1 = _candidate(text="doc b chunk one", document_id=doc_b)
    a2 = _candidate(text="doc a chunk two", document_id=doc_a)

    # Input interleaves documents (as a real fused/reranked result list
    # naturally would); output should group each document's chunks
    # together, in the order each document first appeared.
    result = build_context([a1, b1, a2], max_tokens=1000)

    assert [c.id for c in result] == [a1.id, a2.id, b1.id]


def test_token_budget_stops_at_the_first_candidate_that_does_not_fit() -> None:
    fits = _candidate(text="short")
    too_big = _candidate(text=" ".join(["word"] * 100))
    would_fit_alone = _candidate(text="also short")

    budget = count_tokens("short") + 2  # room for `fits`, not `too_big`
    result = build_context([fits, too_big, would_fit_alone], max_tokens=budget)

    # `would_fit_alone` is skipped too, even though it alone would fit --
    # truncation stops at the boundary rather than reordering to pack
    # more in, preserving the grouped/logical order upstream.
    assert [c.id for c in result] == [fits.id]


def test_a_zero_token_budget_returns_no_chunks() -> None:
    result = build_context([_candidate(text="anything")], max_tokens=0)
    assert result == []


def test_build_context_returns_context_chunks_without_a_score_field() -> None:
    result = build_context([_candidate(text="some content")], max_tokens=1000)
    assert not hasattr(result[0], "score")
    assert result[0].text == "some content"


def test_empty_input_returns_empty_output() -> None:
    assert build_context([], max_tokens=1000) == []
