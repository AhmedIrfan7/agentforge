"""Unit tests for chunking_sentence_paragraph.py (roadmap step 099)."""

import pytest

from chunking_sentence_paragraph import chunk_sentence_paragraph


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_sentence_paragraph("") == []


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_sentence_paragraph("some text", chunk_size=100, overlap=100)


def test_paragraphs_that_fit_become_their_own_chunks() -> None:
    text = (
        "Intro paragraph with a couple sentences here. It sets the stage nicely.\n\n"
        "Second paragraph goes into more detail about the topic at hand.\n\n"
        "Third paragraph wraps things up with a summary for the reader."
    )
    chunks = chunk_sentence_paragraph(text, chunk_size=120, overlap=30)
    assert len(chunks) == 3
    assert chunks[0].text == (
        "Intro paragraph with a couple sentences here. It sets the stage nicely."
    )


def test_full_text_is_covered_with_no_gaps() -> None:
    text = "\n\n".join(f"Paragraph {i} has a short sentence here." for i in range(10))
    chunks = chunk_sentence_paragraph(text, chunk_size=150, overlap=50)
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)


def test_small_paragraphs_get_packed_together_with_real_overlap() -> None:
    text = "\n\n".join(f"Paragraph {i} has a short sentence here." for i in range(10))
    chunks = chunk_sentence_paragraph(text, chunk_size=150, overlap=50)
    assert len(chunks) > 1
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.start < earlier.end  # genuine overlap, not just adjacency


def test_no_chunk_contains_a_partial_paragraph_when_multiple_fit() -> None:
    # Every paragraph boundary in the source text should also be a chunk
    # boundary somewhere -- packing must never cut a paragraph in half
    # when it fits within chunk_size on its own.
    text = "\n\n".join(f"Paragraph {i} has a short sentence here." for i in range(5))
    chunks = chunk_sentence_paragraph(text, chunk_size=200, overlap=40)
    for chunk in chunks:
        assert chunk.text.strip().endswith(".")  # never truncated mid-sentence


def test_oversized_paragraph_falls_back_to_sentence_splitting() -> None:
    big_paragraph = "First sentence in a very long paragraph that has no breaks. " * 5
    chunks = chunk_sentence_paragraph(big_paragraph, chunk_size=150, overlap=30)
    assert len(chunks) > 1
    assert chunks[0].start == 0
    assert chunks[-1].end == len(big_paragraph)
    # Every chunk boundary should land on a real sentence boundary, not
    # mid-sentence -- each chunk's text should end with its terminal
    # punctuation.
    for chunk in chunks:
        assert chunk.text.strip()[-1] in ".!?"


def test_oversized_single_sentence_falls_back_to_fixed_size() -> None:
    # No sentence-ending punctuation anywhere -- must still make
    # progress via chunking_fixed_size's word-safe splitting rather than
    # refusing to chunk or looping forever.
    giant_sentence = "word " * 500
    chunks = chunk_sentence_paragraph(giant_sentence, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert chunks[0].start == 0
    assert chunks[-1].end == len(giant_sentence)


def test_chunk_indices_are_sequential() -> None:
    text = "\n\n".join(f"Paragraph {i} has a short sentence here." for i in range(10))
    chunks = chunk_sentence_paragraph(text, chunk_size=150, overlap=50)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_text_shorter_than_chunk_size_returns_one_chunk() -> None:
    text = "Just one short paragraph, well under the limit."
    chunks = chunk_sentence_paragraph(text, chunk_size=1000, overlap=200)
    assert len(chunks) == 1
    assert chunks[0].text == text
