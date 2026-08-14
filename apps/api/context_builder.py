"""Context builder (roadmap step 126, AGENTS.md "CONTEXT BUILDING" --
"The context builder should become its own module"). Scoped to this
step's own three concrete asks -- dedupe, order, token-budget aware --
not AGENTS.md's full aspirational list for this section: citation
preservation and the richer document/section/page reference system are
step 127's own job ("wire citation-tracking through retrieval->
context->response"), not duplicated here; "remove irrelevant
information" is already retrieval/reranking's own job (steps 120-125),
not re-filtered here.

A standalone, pure module -- same shape as retrieval_fusion.py, not an
agents.retriever.RetrieverAgent method: no async I/O, no external
provider, a deterministic transform over an already-ranked list. Own
ContextCandidate/ContextChunk types, not agents.retriever.
RetrievedChunk -- same layering rule rerankers/base.py's own docstring
established (this module sits below agents/, so it must not import
from it); a caller maps its own richer type down before calling and
back up after. ContextChunk deliberately drops `score` -- a context
chunk's own real output is the text an LLM prompt will actually
receive, and score was only ever a ranking signal for the stages
before this one, the same "own real output shape, not carried-over
upstream baggage" reasoning RerankResult (rerankers/base.py) already
established for dropping `text`.

Real token counting via tiktoken, `text-embedding-3-small`'s own
encoding (cl100k_base, verified live before trusting it) -- the only
real model this codebase currently integrates (embeddings/openai.py,
step 107); no chat/generation model is chosen yet (that's steps
150+), so this is the one honestly known answer today, not a guess at
a future model's tokenizer. Character-count estimation was considered
and rejected: tiktoken is a free, local library with no API key --
there's no honest reason to approximate token counts when a real
measurement is this cheap. Its one real cost: it downloads its BPE
ranks file over the network on first use (verified live, cached to a
local temp dir after) -- no bigger a real dependency than `uv sync`
already needing PyPI access in CI, but a genuine, worth-stating
exception to this module's otherwise fully offline, pure-function
shape.

Grouping (`_group_by_document`), not true in-document ordering: chunks
from the same document are kept adjacent, in their existing relative
order, rather than reordered to match their original position in the
source document (Chunk.index) -- RetrievedChunk doesn't carry `index`
today, and no consumer of this module needs it yet; a documented,
honest limitation rather than a speculative type change with no real
caller to justify it, same "add the field when the step that needs it
lands" discipline used throughout this pipeline.

Token-budget truncation stops at the first candidate that doesn't fit,
rather than skipping ahead to a smaller later one -- preserves the
grouped/logical order this module just built; skipping ahead to
squeeze in more chunks would silently break it.
"""

import uuid
from dataclasses import dataclass

import tiktoken

_ENCODING = tiktoken.encoding_for_model("text-embedding-3-small")


@dataclass(frozen=True)
class ContextCandidate:
    id: uuid.UUID
    document_id: uuid.UUID
    text: str
    score: float


@dataclass(frozen=True)
class ContextChunk:
    id: uuid.UUID
    document_id: uuid.UUID
    text: str


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def build_context(candidates: list[ContextCandidate], *, max_tokens: int) -> list[ContextChunk]:
    deduped = _dedupe(candidates)
    grouped = _group_by_document(deduped)
    return _fit_to_token_budget(grouped, max_tokens)


def _dedupe(candidates: list[ContextCandidate]) -> list[ContextCandidate]:
    # Input is already relevance-ordered by the caller (retrieval and/or
    # reranking, steps 120-125) -- keeping the first occurrence of a
    # normalized text and dropping later ones means the highest-ranked
    # copy always wins, with no extra score bookkeeping needed.
    seen: set[str] = set()
    deduped: list[ContextCandidate] = []
    for candidate in candidates:
        key = candidate.text.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _group_by_document(candidates: list[ContextCandidate]) -> list[ContextCandidate]:
    groups: dict[uuid.UUID, list[ContextCandidate]] = {}
    document_order: list[uuid.UUID] = []
    for candidate in candidates:
        if candidate.document_id not in groups:
            groups[candidate.document_id] = []
            document_order.append(candidate.document_id)
        groups[candidate.document_id].append(candidate)
    return [candidate for document_id in document_order for candidate in groups[document_id]]


def _fit_to_token_budget(candidates: list[ContextCandidate], max_tokens: int) -> list[ContextChunk]:
    fitted: list[ContextChunk] = []
    used_tokens = 0
    for candidate in candidates:
        tokens = count_tokens(candidate.text)
        if used_tokens + tokens > max_tokens:
            break
        fitted.append(
            ContextChunk(id=candidate.id, document_id=candidate.document_id, text=candidate.text)
        )
        used_tokens += tokens
    return fitted
