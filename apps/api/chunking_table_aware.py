"""Table-aware chunker (roadmap step 101) -- the fourth of five chunking
strategies agents/chunking_recommendation.py (step 097) scores and
recommends among. Same "pure algorithm, nothing persisted yet" scope as
the three chunkers before it -- Chunk isn't a DB model until step 105.

Splits text into alternating table and prose regions (a table region is
a contiguous run of "| ... |" lines, matching every extractor's own
table output -- extraction_tables.py:rows_to_markdown -- and
chunking_markdown_heading.py's own heading regex convention of matching
this pipeline's real markdown shape rather than inventing a new one).
Prose regions are split into paragraph/sentence units the same way
chunking_sentence_paragraph.py already does (composed directly, not
reimplemented). Table regions become ONE atomic unit each, no matter
how large -- deliberately never split a table across a chunk boundary,
since a table cut mid-row destroys its meaning far more than an
oversized chunk costs; verified live that a table well over chunk_size
still comes back as exactly one chunk, not silently truncated or torn
apart. Every other chunker in this pipeline caps a chunk at chunk_size;
this is the first one where atomicity deliberately wins over that cap
for a specific unit type, and it's a real, intentional trade-off, not
an oversight.

Packing (small regions combined, overlap at chunk boundaries) reuses
chunking_packing.py:pack_units, the same shared implementation
chunking_sentence_paragraph.py and chunking_markdown_heading.py already
use.
"""

import re

from chunking_packing import pack_units
from chunking_sentence_paragraph import chunk_sentence_paragraph
from chunking_types import Chunk

CHUNK_SIZE = 1000
OVERLAP = 200

_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")

_Span = tuple[int, int]


def _split_table_and_prose_regions(text: str) -> list[tuple[bool, int, int]]:
    """Returns (is_table, start, end) spans covering the whole text --
    a contiguous run of table-shaped lines is one table region;
    everything else (including blank lines between regions) belongs to
    whichever prose region it falls in."""
    lines = text.splitlines(keepends=True)
    regions: list[tuple[bool, int, int]] = []
    pos = 0
    i = 0
    line_count = len(lines)
    while i < line_count:
        is_table = bool(_TABLE_LINE.match(lines[i].rstrip("\n")))
        start = pos
        while i < line_count and bool(_TABLE_LINE.match(lines[i].rstrip("\n"))) == is_table:
            pos += len(lines[i])
            i += 1
        if text[start:pos].strip():
            regions.append((is_table, start, pos))
    return regions


def _build_units(text: str, chunk_size: int) -> list[_Span]:
    units: list[_Span] = []
    for is_table, start, end in _split_table_and_prose_regions(text):
        if is_table:
            units.append((start, end))  # atomic -- never sub-split, see module docstring
        else:
            sub_chunks = chunk_sentence_paragraph(text[start:end], chunk_size=chunk_size, overlap=0)
            units.extend((start + c.start, start + c.end) for c in sub_chunks)
    return units


def chunk_table_aware(
    text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP
) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []
    units = _build_units(text, chunk_size)
    return pack_units(text, units, chunk_size, overlap)
