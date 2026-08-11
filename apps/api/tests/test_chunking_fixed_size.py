"""Unit tests for chunking_fixed_size.py (roadmap step 098)."""

import pytest

from chunking_fixed_size import chunk_fixed_size


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_fixed_size("") == []


def test_text_shorter_than_chunk_size_returns_one_chunk() -> None:
    text = "Just a short piece of text."
    chunks = chunk_fixed_size(text, chunk_size=1000, overlap=200)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].start == 0
    assert chunks[0].end == len(text)
    assert chunks[0].index == 0


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_fixed_size("some text", chunk_size=100, overlap=100)
    with pytest.raises(ValueError):
        chunk_fixed_size("some text", chunk_size=100, overlap=150)


def test_long_text_produces_multiple_chunks_with_overlap() -> None:
    text = "".join(f"word{i} " for i in range(200))
    chunks = chunk_fixed_size(text, chunk_size=50, overlap=10)
    assert len(chunks) > 1
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.start < earlier.end  # consecutive chunks genuinely overlap


def test_chunks_cover_the_full_text_with_no_gaps() -> None:
    text = "".join(f"word{i} " for i in range(200))
    chunks = chunk_fixed_size(text, chunk_size=50, overlap=10)
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)


def test_chunk_indices_are_sequential() -> None:
    text = "".join(f"word{i} " for i in range(200))
    chunks = chunk_fixed_size(text, chunk_size=50, overlap=10)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_no_chunk_end_splits_a_word() -> None:
    # Only chunk ENDS are guaranteed word-aligned (via _snap_to_
    # whitespace) -- a chunk's START can legitimately land mid-word,
    # since it's derived by subtracting a fixed overlap from the
    # previous chunk's already-snapped end, not independently snapped
    # itself. That's fine: the start of an overlap region is run-in
    # context, not expected to be a clean unit on its own.
    text = "The quick brown fox jumps over the lazy dog. " * 20
    chunks = chunk_fixed_size(text, chunk_size=100, overlap=20)
    for chunk in chunks[:-1]:  # the last chunk legitimately ends at len(text), mid-word or not
        assert text[chunk.end - 1].isspace() or text[chunk.end].isspace()


def test_single_pathologically_long_word_does_not_hang() -> None:
    # No whitespace anywhere to snap to -- must degrade to a hard cut
    # rather than loop forever or refuse to chunk at all.
    giant_word = "x" * 5000
    chunks = chunk_fixed_size(giant_word, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert chunks[-1].end == len(giant_word)


def test_reassembling_chunk_text_without_overlap_regions_matches_original() -> None:
    text = "".join(f"word{i} " for i in range(50))
    chunks = chunk_fixed_size(text, chunk_size=50, overlap=10)
    # Each chunk's non-overlapping portion (from its start up to the
    # next chunk's start) should reconstruct the original text exactly.
    reconstructed = "".join(
        text[chunk.start : (chunks[i + 1].start if i + 1 < len(chunks) else chunk.end)]
        for i, chunk in enumerate(chunks)
    )
    assert reconstructed == text
