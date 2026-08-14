"""Unit tests for chunking_table_aware.py (roadmap step 101)."""

import pytest

from chunking_table_aware import chunk_table_aware


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_table_aware("") == []


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_table_aware("some text", chunk_size=100, overlap=100)


def test_text_with_no_table_behaves_like_prose_only() -> None:
    text = "Just an ordinary paragraph of prose with no table anywhere in it at all."
    chunks = chunk_table_aware(text, chunk_size=1000, overlap=200)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_table_never_gets_split_across_chunks() -> None:
    text = (
        "Intro prose here about the data being shown below in the table.\n\n"
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n\n"
        "More prose after the table explaining it further in some detail."
    )
    chunks = chunk_table_aware(text, chunk_size=100, overlap=20)
    table_chunk = next(c for c in chunks if "| A | B |" in c.text)
    assert "| 1 | 2 |" in table_chunk.text
    assert "| 3 | 4 |" in table_chunk.text


def test_oversized_table_still_becomes_exactly_one_chunk() -> None:
    # Atomicity beats the chunk_size cap for tables specifically --
    # deliberate, not a bug -- verified live before trusting it.
    header = "| Col1 | Col2 | Col3 |\n| --- | --- | --- |\n"
    rows = "".join(f"| val{i} | val{i} | val{i} |\n" for i in range(50))
    big_table = header + rows
    chunks = chunk_table_aware(big_table, chunk_size=100, overlap=20)
    assert len(chunks) == 1
    assert chunks[0].text == big_table


def test_multiple_tables_each_stay_atomic() -> None:
    text = (
        "# Title\n\nSome intro prose here about the data.\n\n"
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n\n"
        "More prose after the table explaining it further.\n\n"
        "## Another Table\n\n"
        "| X | Y | Z |\n| --- | --- | --- |\n| 7 | 8 | 9 |\n\n"
        "Final closing prose."
    )
    chunks = chunk_table_aware(text, chunk_size=100, overlap=20)
    combined = "".join(c.text for c in chunks)
    for row in ("| 1 | 2 |", "| 3 | 4 |", "| 7 | 8 | 9 |"):
        assert row in combined
    for chunk in chunks:
        if "| A |" in chunk.text:
            assert "| 1 | 2 |" in chunk.text and "| 3 | 4 |" in chunk.text
        if "| X |" in chunk.text:
            assert "| 7 | 8 | 9 |" in chunk.text


def test_full_text_is_covered_with_no_gaps() -> None:
    text = "Intro prose.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nOutro prose after the table."
    chunks = chunk_table_aware(text, chunk_size=1000, overlap=100)
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)


def test_prose_around_tables_still_gets_paragraph_split() -> None:
    prose = "First real sentence of prose here about something. " * 5
    text = f"{prose}\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n{prose}"
    chunks = chunk_table_aware(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1


def test_chunk_indices_are_sequential() -> None:
    text = (
        "Intro prose.\n\n"
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
        "Outro prose after the table explaining things some more here."
    )
    chunks = chunk_table_aware(text, chunk_size=60, overlap=10)
    assert [c.index for c in chunks] == list(range(len(chunks)))
