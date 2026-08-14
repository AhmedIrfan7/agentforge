"""Tests for multi_query.py (roadmap step 130) -- pure function tests,
no DB/HTTP needed (same reasoning test_retrieval_fusion.py/
test_context_builder.py already established for their own pure
algorithmic modules).
"""

from multi_query import expand_query


def test_a_simple_query_expands_to_only_itself() -> None:
    assert expand_query("refund policy") == ["refund policy"]


def test_an_and_joined_query_splits_into_the_original_plus_both_clauses() -> None:
    result = expand_query("refund policy and shipping times")
    assert result == ["refund policy and shipping times", "refund policy", "shipping times"]


def test_an_or_joined_query_splits_the_same_way() -> None:
    result = expand_query("warranty coverage or return policy")
    assert result == ["warranty coverage or return policy", "warranty coverage", "return policy"]


def test_matching_is_case_insensitive() -> None:
    result = expand_query("refund policy AND shipping times")
    assert "refund policy" in result
    assert "shipping times" in result


def test_comma_separated_clauses_are_split() -> None:
    result = expand_query("refund policy, shipping times")
    assert "refund policy" in result
    assert "shipping times" in result


def test_an_oxford_comma_list_strips_the_leading_conjunction_from_the_last_clause() -> None:
    """A first draft of this heuristic left "and warranty coverage" as
    its own clause instead of "warranty coverage" -- caught by testing
    this exact real-world phrasing pattern, not a hypothetical."""
    result = expand_query("refund policy, shipping times, and warranty coverage")
    assert "warranty coverage" in result
    assert "and warranty coverage" not in result


def test_variant_count_is_capped_so_a_pathological_query_cannot_fan_out_unbounded() -> None:
    result = expand_query("a and b and c and d and e and f and g")
    assert len(result) == 5


def test_a_query_with_a_delimiter_but_no_real_second_clause_is_not_duplicated() -> None:
    # A trailing comma produces only one non-empty clause after
    # splitting, so this counts as "no real split" -- the original
    # query is returned verbatim (untrimmed), not duplicated with a
    # second, merely-whitespace-different variant.
    result = expand_query("refund policy,")
    assert result == ["refund policy,"]
