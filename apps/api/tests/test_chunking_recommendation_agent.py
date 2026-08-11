"""Unit tests for agents/chunking_recommendation.py (roadmap step 097)
-- one case per strategy this agent can recommend, plus the tie-break
fix that made recursive_hybrid actually reachable at all.
"""

from agents.chunking_recommendation import ChunkingRecommendationAgent

agent = ChunkingRecommendationAgent()


def test_unstructured_text_recommends_fixed_size() -> None:
    text = "just a short blob of text with no structure at all really"
    result = agent.recommend(text)
    assert result.strategy == "fixed_size"


def test_paragraphed_prose_recommends_sentence_paragraph() -> None:
    text = (
        "First paragraph of real prose here, several sentences long indeed.\n\n"
        "Second paragraph continues the narrative further along nicely.\n\n"
        "Third paragraph wraps up the point being made overall.\n\n"
        "Fourth paragraph adds one more for good measure here."
    )
    result = agent.recommend(text)
    assert result.strategy == "sentence_paragraph"


def test_multiple_headings_recommends_markdown_heading() -> None:
    text = (
        "# Title\n\nIntro text.\n\n"
        "## Section One\n\nBody one.\n\n"
        "## Section Two\n\nBody two.\n\n"
        "## Section Three\n\nBody three."
    )
    result = agent.recommend(text)
    assert result.strategy == "markdown_heading"


def test_table_heavy_document_recommends_table_aware() -> None:
    text = (
        "# Data\n\n"
        "| A | B | C |\n| --- | --- | --- |\n"
        "| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n| 7 | 8 | 9 |\n| 10 | 11 | 12 |"
    )
    result = agent.recommend(text)
    assert result.strategy == "table_aware"


def test_mixed_tables_and_headings_recommends_recursive_hybrid() -> None:
    # A document that's strongly BOTH table-heavy and heading-heavy at
    # once used to lose the tie to table_aware (both scored a capped
    # 1.0, and table_aware was checked first) -- this is the case that
    # caught it: recursive_hybrid must win a genuine tie against the
    # strategies it exists to combine, not lose to whichever is listed
    # earlier.
    text = (
        "# T1\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
        "## T2\n\nprose\n\n## T3\n\nmore prose\n\n## T4\n\neven more"
    )
    result = agent.recommend(text)
    assert result.strategy == "recursive_hybrid"
    assert result.scores["recursive_hybrid"] >= result.scores["table_aware"]
    assert result.scores["recursive_hybrid"] >= result.scores["markdown_heading"]


def test_very_large_document_recommends_recursive_hybrid() -> None:
    text = "## Section\n\nSome prose here.\n\n" * 1000
    result = agent.recommend(text)
    assert result.strategy == "recursive_hybrid"


def test_all_five_strategies_are_always_scored() -> None:
    result = agent.recommend("some arbitrary text")
    assert set(result.scores.keys()) == {
        "fixed_size",
        "sentence_paragraph",
        "markdown_heading",
        "table_aware",
        "recursive_hybrid",
    }
    assert all(0.0 <= score <= 1.0 for score in result.scores.values())


def test_reasoning_names_the_winning_strategy() -> None:
    result = agent.recommend("# Title\n\n## A\n\n## B\n\n## C")
    assert result.strategy in result.reasoning


def test_empty_text_falls_back_to_fixed_size() -> None:
    result = agent.recommend("")
    assert result.strategy == "fixed_size"
