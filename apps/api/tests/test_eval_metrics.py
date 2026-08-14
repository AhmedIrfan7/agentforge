"""Tests for eval/metrics.py (roadmap step 128) -- pure function tests
against the standard, well-known precision@k/recall@k formulas.
"""

import uuid

from eval.metrics import precision_at_k, recall_at_k


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def test_precision_is_the_fraction_of_top_k_that_are_relevant() -> None:
    relevant_a, relevant_b, irrelevant = _ids(3)
    retrieved = [relevant_a, irrelevant, relevant_b]

    assert precision_at_k(retrieved, {relevant_a, relevant_b}, k=3) == 2 / 3


def test_precision_only_looks_at_the_top_k_even_if_more_are_retrieved() -> None:
    relevant, irrelevant_1, irrelevant_2 = _ids(3)
    retrieved = [irrelevant_1, irrelevant_2, relevant]

    assert precision_at_k(retrieved, {relevant}, k=2) == 0.0


def test_precision_on_empty_retrieved_list_is_zero() -> None:
    assert precision_at_k([], {uuid.uuid4()}, k=5) == 0.0


def test_recall_is_the_fraction_of_relevant_items_found() -> None:
    relevant_a, relevant_b, relevant_c = _ids(3)
    retrieved = [relevant_a]

    assert recall_at_k(retrieved, {relevant_a, relevant_b, relevant_c}, k=5) == 1 / 3


def test_recall_with_no_relevant_items_is_zero_not_a_division_error() -> None:
    assert recall_at_k([uuid.uuid4()], set(), k=5) == 0.0


def test_recall_only_looks_at_the_top_k() -> None:
    relevant = uuid.uuid4()
    filler = _ids(5)
    retrieved = [*filler, relevant]  # relevant item ranked 6th

    assert recall_at_k(retrieved, {relevant}, k=5) == 0.0


def test_perfect_retrieval_scores_one_on_both_metrics() -> None:
    relevant_a, relevant_b = _ids(2)
    retrieved = [relevant_a, relevant_b]

    assert precision_at_k(retrieved, {relevant_a, relevant_b}, k=2) == 1.0
    assert recall_at_k(retrieved, {relevant_a, relevant_b}, k=2) == 1.0
