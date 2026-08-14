"""Shared text-region splitters (roadmap step 100/101, promoted to
public/shared here in step 102 once chunking_recursive_hybrid.py needed
BOTH -- heading sections and table/prose regions -- together in one
place, rather than each staying a private helper duplicated or
re-derived in its own chunker module. Same "build inline for the first
consumer, promote once a second one needs it" pattern already used
repeatedly across this pipeline (Chunk, rows_to_markdown, pack_units).

split_sections (originally chunking_markdown_heading.py's private
_split_sections) and split_table_and_prose_regions (originally
chunking_table_aware.py's private _split_table_and_prose_regions) are
otherwise unchanged -- moved, not rewritten.
"""

import re

_HEADING_LINE = re.compile(r"^#{1,6}\s.*$", re.MULTILINE)
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")

Span = tuple[int, int]


def split_sections(text: str) -> list[Span]:
    """Each span is a heading line plus everything up to the next
    heading of any level, or the end of the document. Content before
    the first heading (if any) is its own leading, headingless
    section."""
    matches = list(_HEADING_LINE.finditer(text))
    if not matches:
        return [(0, len(text))] if text.strip() else []

    spans: list[Span] = []
    if matches[0].start() > 0 and text[: matches[0].start()].strip():
        spans.append((0, matches[0].start()))
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if text[start:end].strip():
            spans.append((start, end))
    return spans


def split_table_and_prose_regions(text: str) -> list[tuple[bool, int, int]]:
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
