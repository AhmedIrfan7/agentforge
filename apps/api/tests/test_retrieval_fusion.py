"""Tests for retrieval_fusion.py (roadmap step 122) -- pure function,
no DB/HTTP needed, verifying the real RRF formula (1/(k+rank), summed
across lists) rather than just that it runs.
"""

import uuid

from retrieval_fusion import reciprocal_rank_fusion


def test_chunk_ranked_first_in_both_lists_scores_highest() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b, c], [a, c, b]])

    assert scores[a] > scores[b]
    assert scores[a] > scores[c]


def test_score_matches_the_real_rrf_formula() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b]], k=60)

    assert scores[a] == 1.0 / 61
    assert scores[b] == 1.0 / 62


def test_a_chunk_present_in_both_lists_sums_its_contributions() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b], [b, a]], k=60)

    # a: rank 1 in list one, rank 2 in list two
    # b: rank 2 in list one, rank 1 in list two -- same total, by symmetry
    assert scores[a] == 1.0 / 61 + 1.0 / 62
    assert scores[b] == 1.0 / 62 + 1.0 / 61
    assert scores[a] == scores[b]


def test_a_chunk_present_in_only_one_list_still_gets_a_real_score() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a], []], k=60)

    assert scores == {a: 1.0 / 61}
    assert b not in scores


def test_a_chunk_appearing_earlier_in_one_list_ranks_above_one_only_in_another() -> None:
    """A chunk appearing in BOTH lists (even at modest ranks) should
    usually outrank a chunk appearing in only one list at rank 1 -- the
    whole point of fusing two independent signals."""
    only_in_one, in_both = uuid.uuid4(), uuid.uuid4()
    other = uuid.uuid4()
    scores = reciprocal_rank_fusion([[only_in_one, in_both, other], [in_both, other]])

    assert scores[in_both] > scores[only_in_one]


def test_empty_rankings_produce_no_scores() -> None:
    assert reciprocal_rank_fusion([]) == {}
    assert reciprocal_rank_fusion([[], []]) == {}
