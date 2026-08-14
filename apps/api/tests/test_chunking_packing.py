"""Unit tests for chunking_packing.py (roadmap step 100, promoted out of
chunking_sentence_paragraph.py's own step-099 implementation) -- exercised
directly against synthetic unit spans, independent of any particular
chunker's own unit-building logic.
"""

from chunking_packing import pack_units


def test_no_units_returns_no_chunks() -> None:
    assert pack_units("some text", [], chunk_size=100, overlap=20) == []


def test_single_small_unit_becomes_one_chunk() -> None:
    text = "Hello world"
    chunks = pack_units(text, [(0, 11)], chunk_size=100, overlap=20)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].start == 0
    assert chunks[0].end == 11
    assert chunks[0].index == 0


def test_small_units_get_packed_into_one_chunk_when_they_fit() -> None:
    text = "aaaaabbbbbccccc"
    units = [(0, 5), (5, 10), (10, 15)]
    chunks = pack_units(text, units, chunk_size=100, overlap=0)
    assert len(chunks) == 1
    assert chunks[0].start == 0
    assert chunks[0].end == 15


def test_units_split_across_chunks_when_they_do_not_all_fit() -> None:
    text = "a" * 10 + "b" * 10 + "c" * 10
    units = [(0, 10), (10, 20), (20, 30)]
    chunks = pack_units(text, units, chunk_size=15, overlap=0)
    assert len(chunks) > 1
    assert chunks[0].end <= 15


def test_overlap_repeats_trailing_units_in_next_chunk() -> None:
    text = "a" * 10 + "b" * 10 + "c" * 10 + "d" * 10
    units = [(0, 10), (10, 20), (20, 30), (30, 40)]
    chunks = pack_units(text, units, chunk_size=20, overlap=10)
    assert len(chunks) > 1
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.start < earlier.end


def test_full_coverage_with_no_gaps() -> None:
    text = "".join(f"unit{i}-" for i in range(20))
    units = []
    pos = 0
    for _ in range(20):
        end = text.index("-", pos) + 1
        units.append((pos, end))
        pos = end
    chunks = pack_units(text, units, chunk_size=20, overlap=5)
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)


def test_indices_are_sequential() -> None:
    text = "a" * 10 + "b" * 10 + "c" * 10
    units = [(0, 10), (10, 20), (20, 30)]
    chunks = pack_units(text, units, chunk_size=12, overlap=2)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_single_oversized_unit_gets_its_own_chunk_with_no_overlap_source() -> None:
    # A chunk made of one unit bigger than chunk_size has no smaller
    # piece to draw overlap from -- must still make forward progress,
    # not loop or crash.
    text = "x" * 500
    units = [(0, 500)]
    chunks = pack_units(text, units, chunk_size=100, overlap=20)
    assert len(chunks) == 1
    assert chunks[0].start == 0
    assert chunks[0].end == 500
