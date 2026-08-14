"""Shared unit-level packing algorithm (roadmap step 099, promoted out
of chunking_sentence_paragraph.py in step 100 once a second chunker --
chunking_markdown_heading.py -- needed the identical logic byte for
byte). Same "build inline for the first consumer, promote once a second
one needs it" pattern chunking_types.py's Chunk and extraction_tables.py's
rows_to_markdown already used elsewhere in this pipeline.

Takes any list of (start, end) unit spans -- paragraphs, sentences,
markdown sections, whatever the caller's own unit-building logic
produced -- and greedily packs consecutive units into chunks up to
chunk_size, with overlap re-including whichever trailing units of a
finished chunk add up to at least `overlap` characters. Deliberately
generic over what a "unit" means; the caller owns deciding what the
natural boundaries are for its own strategy.
"""

from chunking_types import Chunk

Span = tuple[int, int]


def pack_units(text: str, units: list[Span], chunk_size: int, overlap: int) -> list[Chunk]:
    if not units:
        return []

    chunks: list[Chunk] = []
    index = 0
    i = 0
    unit_count = len(units)
    while i < unit_count:
        chunk_start = units[i][0]
        j = i
        chunk_end = units[j][1]
        while j + 1 < unit_count and (units[j + 1][1] - chunk_start) <= chunk_size:
            j += 1
            chunk_end = units[j][1]

        chunks.append(
            Chunk(text=text[chunk_start:chunk_end], start=chunk_start, end=chunk_end, index=index)
        )
        index += 1
        if j == unit_count - 1:
            break

        # Walk backward from the last included unit to find how many
        # trailing units are needed to cover at least `overlap`
        # characters -- those repeat at the start of the next chunk.
        k = j
        while k > i and (chunk_end - units[k][0]) < overlap:
            k -= 1
        # max(..., i + 1): guarantees forward progress -- a chunk made
        # of one oversized unit (k == i == j) has no trailing unit to
        # overlap with (see each caller's own module docstring).
        i = max(k, i + 1)
    return chunks
