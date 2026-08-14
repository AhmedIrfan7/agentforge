"""Markdown/heading-aware chunker (roadmap step 100) -- the third of
five chunking strategies agents/chunking_recommendation.py (step 097)
scores and recommends among. Same "pure algorithm, nothing persisted
yet" scope as chunking_fixed_size.py/chunking_sentence_paragraph.py --
Chunk isn't a DB model until step 105.

Splits along markdown heading boundaries ("# "/"## " through six
levels, matching every extractor in this pipeline's own output --
extraction_pdf.py, extraction_docx.py, etc. -- since they all already
produce this exact heading shape). A "section" is a heading line plus
everything up to the next heading of any level, or the end of the
document; content before the first heading (if any) is its own leading,
headingless section. Small adjacent sections get packed together into
one chunk, same unit-level packing-with-overlap approach
chunking_sentence_paragraph.py uses, just with sections as the unit
instead of paragraphs -- an oversized section falls back to
chunk_sentence_paragraph for its own content, composing the existing
chunker rather than re-implementing paragraph/sentence packing a third
time.

Known, accepted limitation: when an oversized section gets sub-split,
only its first resulting piece visibly starts with the section's
heading text -- later pieces from that same section don't have the
heading text repeated into them. Chunk.text is always an exact
substring of the source (text == original_text[start:end], the same
invariant chunking_fixed_size.py and chunking_sentence_paragraph.py
both hold), so re-injecting the heading into every sub-chunk would mean
either breaking that invariant or inventing a second field just for
this one strategy -- not worth it for what's still a rare case (only
sections too large for chunk_size on their own even hit this path).
"""

import re

from chunking_packing import pack_units
from chunking_sentence_paragraph import chunk_sentence_paragraph
from chunking_types import Chunk

CHUNK_SIZE = 1000
OVERLAP = 200

_HEADING_LINE = re.compile(r"^#{1,6}\s.*$", re.MULTILINE)

_Span = tuple[int, int]


def _split_sections(text: str) -> list[_Span]:
    matches = list(_HEADING_LINE.finditer(text))
    if not matches:
        return [(0, len(text))] if text.strip() else []

    spans: list[_Span] = []
    if matches[0].start() > 0 and text[: matches[0].start()].strip():
        spans.append((0, matches[0].start()))
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if text[start:end].strip():
            spans.append((start, end))
    return spans


def _build_units(text: str, chunk_size: int) -> list[_Span]:
    units: list[_Span] = []
    for section_start, section_end in _split_sections(text):
        if section_end - section_start <= chunk_size:
            units.append((section_start, section_end))
            continue
        sub_chunks = chunk_sentence_paragraph(
            text[section_start:section_end], chunk_size=chunk_size, overlap=0
        )
        units.extend((section_start + c.start, section_start + c.end) for c in sub_chunks)
    return units


def chunk_markdown_heading(
    text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP
) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []
    units = _build_units(text, chunk_size)
    return pack_units(text, units, chunk_size, overlap)
