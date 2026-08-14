"""Unit tests for chunking_markdown_heading.py (roadmap step 100)."""

import pytest

from chunking_markdown_heading import chunk_markdown_heading


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_markdown_heading("") == []


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_markdown_heading("some text", chunk_size=100, overlap=100)


def test_text_with_no_headings_is_one_section() -> None:
    text = "Just plain text with no markdown headings anywhere in it at all."
    chunks = chunk_markdown_heading(text, chunk_size=1000, overlap=200)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_content_before_first_heading_is_its_own_leading_section() -> None:
    text = "Intro before any heading.\n\n# Title\n\nBody under the title."
    chunks = chunk_markdown_heading(text, chunk_size=1000, overlap=200)
    # Both pieces fit comfortably within one chunk together, but the
    # leading headingless content must still be present and untouched.
    assert "Intro before any heading." in chunks[0].text
    assert "# Title" in chunks[0].text


def test_sections_that_fit_stay_whole_and_keep_their_heading() -> None:
    text = (
        "# Title\n\nIntro.\n\n"
        "## Section A\n\nBody A here, some real detail in it.\n\n"
        "## Section B\n\nBody B here, some real detail in it too."
    )
    chunks = chunk_markdown_heading(text, chunk_size=45, overlap=10)
    assert len(chunks) >= 2
    # Every section heading that appears in the source should appear
    # attached to its own body somewhere in the output.
    combined = " ".join(c.text for c in chunks)
    assert "## Section A" in combined
    assert "## Section B" in combined


def test_full_text_is_covered_with_no_gaps() -> None:
    text = "# Title\n\nIntro.\n\n## A\n\nShort A.\n\n## B\n\nShort B.\n\n## C\n\nShort C."
    chunks = chunk_markdown_heading(text, chunk_size=60, overlap=15)
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)


def test_small_sections_get_packed_together_with_real_overlap() -> None:
    text = "# Title\n\nIntro.\n\n## A\n\nShort A.\n\n## B\n\nShort B.\n\n## C\n\nShort C."
    chunks = chunk_markdown_heading(text, chunk_size=60, overlap=15)
    assert len(chunks) > 1
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.start < earlier.end


def test_oversized_section_falls_back_to_sentence_paragraph_splitting() -> None:
    big_section = "## Big Section\n\n" + ("A sentence in the big section body. " * 10)
    chunks = chunk_markdown_heading(big_section, chunk_size=150, overlap=30)
    assert len(chunks) > 1
    assert chunks[0].start == 0
    assert chunks[-1].end == len(big_section)
    assert "## Big Section" in chunks[0].text


def test_headings_up_to_level_six_are_recognized() -> None:
    text = "###### Deepest Heading\n\nSome content under it."
    chunks = chunk_markdown_heading(text, chunk_size=1000, overlap=200)
    assert "###### Deepest Heading" in chunks[0].text


def test_a_hash_not_at_line_start_is_not_treated_as_a_heading() -> None:
    text = "Some text with a # not at line start.\n\nMore text after it."
    chunks = chunk_markdown_heading(text, chunk_size=1000, overlap=200)
    assert len(chunks) == 1  # no real heading found, whole thing is one section


def test_chunk_indices_are_sequential() -> None:
    text = "# Title\n\nIntro.\n\n## A\n\nShort A.\n\n## B\n\nShort B.\n\n## C\n\nShort C."
    chunks = chunk_markdown_heading(text, chunk_size=60, overlap=15)
    assert [c.index for c in chunks] == list(range(len(chunks)))
