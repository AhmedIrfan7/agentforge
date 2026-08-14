"""Unit tests for chunking_regions.py (roadmap step 102, promoted out of
chunking_markdown_heading.py's and chunking_table_aware.py's own
step-100/101 implementations)."""

from chunking_regions import split_sections, split_table_and_prose_regions


def test_split_sections_no_headings_is_one_section() -> None:
    text = "Just plain text with no markdown headings anywhere in it."
    assert split_sections(text) == [(0, len(text))]


def test_split_sections_empty_text_returns_nothing() -> None:
    assert split_sections("") == []


def test_split_sections_content_before_first_heading_is_leading_section() -> None:
    text = "Intro.\n\n# Title\n\nBody."
    spans = split_sections(text)
    assert len(spans) == 2
    assert text[spans[0][0] : spans[0][1]] == "Intro.\n\n"


def test_split_sections_handles_extra_blank_lines_between_headings() -> None:
    text = "# A\n\nBody A.\n\n\n# B\n\nBody B."
    spans = split_sections(text)
    reconstructed_has_no_gap = spans[0][1] <= spans[1][0]
    assert reconstructed_has_no_gap
    assert "# B" in text[spans[1][0] : spans[1][1]]


def test_split_table_and_prose_regions_isolates_tables() -> None:
    text = "Prose before.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nProse after."
    regions = split_table_and_prose_regions(text)
    table_regions = [r for r in regions if r[0]]
    assert len(table_regions) == 1
    _, s, e = table_regions[0]
    assert "| A | B |" in text[s:e]
    assert "| 1 | 2 |" in text[s:e]
    assert "Prose before" not in text[s:e]


def test_split_table_and_prose_regions_covers_full_text() -> None:
    text = "Prose before.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nProse after."
    regions = split_table_and_prose_regions(text)
    assert regions[0][1] == 0
    assert regions[-1][2] == len(text)


def test_split_table_and_prose_regions_no_table_is_one_prose_region() -> None:
    text = "Just plain prose, no table anywhere in this text at all."
    regions = split_table_and_prose_regions(text)
    assert len(regions) == 1
    assert regions[0][0] is False
