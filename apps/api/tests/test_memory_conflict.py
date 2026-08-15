"""Tests for memory_conflict.py (roadmap step 173)."""

import uuid

from memory_conflict import content_overlap_ratio, find_conflicting_memory
from models.memory import Memory


def _memory(content: str, *, importance_score: float = 0.7) -> Memory:
    return Memory(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        scope="session",
        content=content,
        importance_score=importance_score,
    )


def test_content_overlap_ratio_is_one_for_identical_content() -> None:
    assert content_overlap_ratio("Jordan prefers email", "Jordan prefers email") == 1.0


def test_content_overlap_ratio_is_zero_for_disjoint_content() -> None:
    assert content_overlap_ratio("Jordan prefers email", "The weather is nice today") == 0.0


def test_content_overlap_ratio_is_partial_for_overlapping_content() -> None:
    ratio = content_overlap_ratio("Jordan prefers email over chat", "Jordan strongly prefers email")
    assert 0.0 < ratio < 1.0


def test_content_overlap_ratio_ignores_case_and_punctuation() -> None:
    assert content_overlap_ratio("Jordan's email!", "jordans email") == 1.0


def test_find_conflicting_memory_returns_the_overlapping_candidate() -> None:
    existing = _memory("Jordan prefers email over chat.")
    other = _memory("Completely unrelated fact about shipping times.")

    result = find_conflicting_memory([other, existing], "Jordan prefers email.")

    assert result is existing


def test_find_conflicting_memory_returns_none_when_nothing_overlaps_enough() -> None:
    candidates = [_memory("Completely unrelated fact.")]

    result = find_conflicting_memory(candidates, "Jordan prefers email.")

    assert result is None


def test_find_conflicting_memory_returns_none_for_an_empty_candidate_list() -> None:
    assert find_conflicting_memory([], "Jordan prefers email.") is None
