"""Unit tests for chunking_recursive_hybrid.py (roadmap step 102)."""

import pytest

from chunking_recursive_hybrid import chunk_recursive_hybrid


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_recursive_hybrid("") == []


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_recursive_hybrid("some text", chunk_size=100, overlap=100)


def test_small_document_with_no_structure_stays_one_chunk() -> None:
    text = "Just a short piece of unstructured text."
    chunks = chunk_recursive_hybrid(text, chunk_size=1000, overlap=200)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_table_inside_an_oversized_section_stays_whole() -> None:
    # The one case neither chunking_markdown_heading.py nor
    # chunking_table_aware.py alone gets right: a section too big to
    # keep whole, containing a table, must still not have that table
    # torn apart by the sentence-splitting fallback.
    text = (
        "# Report\n\nIntro paragraph before any subsection appears here at all.\n\n"
        "## Revenue\n\n"
        "Some prose explaining the numbers in detail before the table appears below.\n\n"
        "| Region | Revenue |\n| --- | --- |\n| North | 120000 |\n| South | 98000 |\n\n"
        "More prose after the table wrapping up this subsection with commentary.\n\n"
        "## Notes\n\nShort notes section here."
    )
    chunks = chunk_recursive_hybrid(text, chunk_size=120, overlap=25)
    table_chunk = next(c for c in chunks if "| Region | Revenue |" in c.text)
    assert "| North | 120000 |" in table_chunk.text
    assert "| South | 98000 |" in table_chunk.text


def test_full_text_is_covered_with_no_gaps() -> None:
    text = (
        "# Report\n\nIntro.\n\n"
        "## Revenue\n\nProse.\n\n"
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
        "More prose.\n\n## Notes\n\nShort notes."
    )
    chunks = chunk_recursive_hybrid(text, chunk_size=120, overlap=25)
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)


def test_small_sections_get_packed_together_with_real_overlap() -> None:
    text = "## A\n\nShort A.\n\n## B\n\nShort B.\n\n## C\n\nShort C.\n\n## D\n\nShort D."
    chunks = chunk_recursive_hybrid(text, chunk_size=40, overlap=10)
    assert len(chunks) > 1
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.start < earlier.end


def test_document_with_no_headings_falls_back_to_table_prose_handling() -> None:
    text = "Prose before.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nProse after."
    chunks = chunk_recursive_hybrid(text, chunk_size=1000, overlap=100)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_chunk_indices_are_sequential() -> None:
    text = "## A\n\nShort A.\n\n## B\n\nShort B.\n\n## C\n\nShort C."
    chunks = chunk_recursive_hybrid(text, chunk_size=40, overlap=10)
    assert [c.index for c in chunks] == list(range(len(chunks)))
