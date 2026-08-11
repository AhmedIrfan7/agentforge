"""Fixed-size chunker (roadmap step 098) -- the first of five chunking
strategies agents/chunking_recommendation.py (step 097) scores and
recommends among. A pure algorithm only: nothing persists a Chunk yet
(that model doesn't exist until step 105), and nothing dispatches real
chunking yet either -- that lands once all five strategies (098-102)
and the decision-persistence step (104) are in place.

Character-based, not token-based: no tokenizer is wired into this
project yet -- embedding providers, the thing that would actually
dictate a token budget, don't land until step 107 -- and picking one
now would tie this chunker to whichever provider's tokenizer arbitrarily,
before there's a real provider to tie it to.

Splits every CHUNK_SIZE characters, snapped back to the nearest
whitespace before the boundary so a chunk doesn't end mid-word -- basic
hygiene, not the sentence/paragraph awareness step 099 owns. Falls back
to a hard cut only when no whitespace exists within the lookback window
(one pathologically long "word" -- a URL, a hash), verified live rather
than assumed to degrade gracefully. OVERLAP characters of context
repeat at the start of each chunk after the first, a standard RAG
technique so a fact sitting right at a chunk boundary isn't truncated
away for every retrieval that touches it.
"""

from dataclasses import dataclass

CHUNK_SIZE = 1000
OVERLAP = 200


@dataclass
class Chunk:
    text: str
    start: int
    end: int
    index: int


def _snap_to_whitespace(text: str, boundary: int, lookback_limit: int) -> int:
    earliest = max(boundary - lookback_limit, 0)
    i = boundary
    while i > earliest:
        if text[i - 1].isspace():
            return i
        i -= 1
    return boundary  # no whitespace within the lookback window -- cut mid-word rather than loop


def chunk_fixed_size(
    text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP
) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []

    chunks: list[Chunk] = []
    start = 0
    index = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            end = _snap_to_whitespace(text, end, chunk_size // 2)
        chunk_text = text[start:end]
        if chunk_text.strip():
            chunks.append(Chunk(text=chunk_text, start=start, end=end, index=index))
            index += 1
        if end >= length:
            break
        # max(..., start + 1): guarantees forward progress even if
        # snapping moved `end` back far enough that end - overlap would
        # otherwise not advance past the current start (an infinite loop).
        start = max(end - overlap, start + 1)
    return chunks
