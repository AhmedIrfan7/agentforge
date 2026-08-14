"""Sentence/paragraph-aware chunker (roadmap step 099) -- the second of
five chunking strategies agents/chunking_recommendation.py (step 097)
scores and recommends among. Same "pure algorithm, nothing persisted
yet" scope as chunking_fixed_size.py (step 098) -- Chunk isn't a DB
model until step 105.

Where fixed-size chunking splits blindly by character count (snapped
only far enough to avoid a mid-word cut), this respects real text
structure: whole paragraphs are kept together when they fit, an
oversized paragraph is split into whole sentences instead, and only an
individual sentence that's STILL too long on its own falls all the way
back to chunk_fixed_size's raw character splitting -- composing the two
chunkers rather than duplicating word-safe splitting logic a second
time.

Sentence splitting is a real, bounded regex heuristic (punctuation
followed by whitespace followed by a capital letter), not a full NLP
sentence tokenizer -- same "honest about not being ML/NLP" stance as
extraction_pdf.py's font-size heading heuristic. Verified live against
real text before trusting it: handles ordinary sentences, questions,
and decimals ("3.14") correctly, but a genuine, known limitation is
mid-sentence abbreviations ("Dr. Smith" splits after "Dr."). This
doesn't meaningfully hurt chunking quality in practice -- a mis-split
abbreviation just becomes a very short unit that gets packed back in
with its neighbors during packing (chunking_packing.py), same as any
other short sentence would be.

Packing is unit-level (whole paragraphs/sentences), not character-
level -- chunking_packing.py:pack_units (promoted to shared in step 100
once chunking_markdown_heading.py needed the identical packing logic).
A chunk made of a single oversized unit has no smaller natural piece to
overlap with without violating the whole point of this strategy (never
splitting a sentence/paragraph mid-unit) -- an honest, inherent
trade-off of unit-level overlap, not a bug.
"""

import re

from chunking_fixed_size import chunk_fixed_size
from chunking_packing import pack_units
from chunking_types import Chunk

CHUNK_SIZE = 1000
OVERLAP = 200

_PARAGRAPH_SEPARATOR = re.compile(r"\n\s*\n")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

_Span = tuple[int, int]


def _split_paragraphs(text: str) -> list[_Span]:
    spans: list[_Span] = []
    pos = 0
    for match in _PARAGRAPH_SEPARATOR.finditer(text):
        if text[pos : match.start()].strip():
            spans.append((pos, match.start()))
        pos = match.end()
    if text[pos:].strip():
        spans.append((pos, len(text)))
    return spans


def _split_sentences(text: str, base_offset: int) -> list[_Span]:
    spans: list[_Span] = []
    pos = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        if text[pos : match.start()].strip():
            spans.append((base_offset + pos, base_offset + match.start()))
        pos = match.end()
    if text[pos:].strip():
        spans.append((base_offset + pos, base_offset + len(text)))
    return spans


def _build_units(text: str, chunk_size: int) -> list[_Span]:
    units: list[_Span] = []
    for para_start, para_end in _split_paragraphs(text):
        if para_end - para_start <= chunk_size:
            units.append((para_start, para_end))
            continue
        for sent_start, sent_end in _split_sentences(text[para_start:para_end], para_start):
            if sent_end - sent_start <= chunk_size:
                units.append((sent_start, sent_end))
            else:
                # A single sentence longer than chunk_size on its own --
                # reuse the fixed-size chunker's word-safe splitting for
                # just this span rather than re-implementing it, then
                # shift its (already-correct, relative) offsets back to
                # absolute positions in the original text.
                sub_chunks = chunk_fixed_size(
                    text[sent_start:sent_end], chunk_size=chunk_size, overlap=0
                )
                units.extend((sent_start + c.start, sent_start + c.end) for c in sub_chunks)
    return units


def chunk_sentence_paragraph(
    text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP
) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []
    units = _build_units(text, chunk_size)
    return pack_units(text, units, chunk_size, overlap)
