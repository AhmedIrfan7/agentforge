"""Recursive/hybrid chunker (roadmap step 102) -- the fifth and last of
five chunking strategies agents/chunking_recommendation.py (step 097)
scores and recommends among. Same "pure algorithm, nothing persisted
yet" scope as the four chunkers before it -- Chunk isn't a DB model
until step 105.

Where each of the other four strategies handles exactly one structural
dimension well (chunking_markdown_heading.py respects sections but
doesn't protect tables inside an oversized one from
chunking_sentence_paragraph.py's sentence-splitting fallback;
chunking_table_aware.py protects tables but has no concept of heading
sections at all), this one is genuinely hybrid: split by heading
section first (chunking_regions.py:split_sections), then, only within
whichever sections are too big to keep whole, protect tables as atomic
units and pack the surrounding prose by paragraph/sentence
(chunking_regions.py:split_table_and_prose_regions +
chunk_sentence_paragraph) -- composing three existing building blocks
recursively rather than inventing a new splitting technique. This is
exactly the combination agents/chunking_recommendation.py's own scoring
targets: it recommends this strategy specifically when a document has
BOTH strong table AND strong heading signals at once, a combination
none of the other four chunkers handle correctly together. Verified
live against a document with a table sitting inside an oversized
section: the table came back completely whole, not torn apart by
sentence-splitting the way running chunking_markdown_heading.py alone
over the same document would risk.

Packing reuses chunking_packing.py:pack_units, same shared
implementation every other strategy in this pipeline uses.
"""

from chunking_packing import pack_units
from chunking_regions import Span, split_sections, split_table_and_prose_regions
from chunking_sentence_paragraph import chunk_sentence_paragraph
from chunking_types import Chunk

CHUNK_SIZE = 1000
OVERLAP = 200


def _build_units(text: str, chunk_size: int) -> list[Span]:
    units: list[Span] = []
    for section_start, section_end in split_sections(text):
        if section_end - section_start <= chunk_size:
            units.append((section_start, section_end))
            continue

        section_text = text[section_start:section_end]
        for is_table, region_start, region_end in split_table_and_prose_regions(section_text):
            abs_start = section_start + region_start
            abs_end = section_start + region_end
            if is_table:
                units.append((abs_start, abs_end))  # atomic, same rule chunking_table_aware.py uses
            else:
                sub_chunks = chunk_sentence_paragraph(
                    text[abs_start:abs_end], chunk_size=chunk_size, overlap=0
                )
                units.extend((abs_start + c.start, abs_start + c.end) for c in sub_chunks)
    return units


def chunk_recursive_hybrid(
    text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP
) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []
    units = _build_units(text, chunk_size)
    return pack_units(text, units, chunk_size, overlap)
