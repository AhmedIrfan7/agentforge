"""Chunking Recommendation Agent (roadmap step 097, AGENTS.md SECTION 5
"INTELLIGENT CHUNKING") -- scores candidate chunking strategies against
a document's actual structure and recommends one, with an explanation.
A skeleton in the same sense step 095's DocumentAnalysisAgent was: none
of the five strategies it recommends among (fixed_size, sentence_
paragraph, markdown_heading, table_aware, recursive_hybrid) have a real
chunker implementation yet -- those are steps 098-102. This agent's own
deliverable is the recommendation itself; something for a later step
(103's override endpoint, and whichever step actually dispatches
chunking) to act on, the same "build the primitive now, the feature
that consumes it later" split step 096's content_hash used for step
117.

Scoring is heuristic, not an ML model or LLM call -- structural signals
counted directly from the extracted markdown text (heading lines, table
lines, paragraph breaks, overall length), same "honest about not being
ML" stance as extraction_pdf.py's font-size heuristic and step 095's
keyword classifier. All five strategies get a score in [0, 1], not just
the winner -- AGENTS.md's own framing for this agent is "compare them,
score them," not "pick one silently."

Every extractor in this pipeline (extraction_pdf.py, extraction_docx.py,
etc.) already produces the same markdown shape ("# "/"## " headings,
"| ... |" pipe tables), which is exactly what makes one structural
scoring pass work uniformly across every source format -- this agent
doesn't need to know whether a document originated as a PDF, DOCX, or
plain markdown file.
"""

import re
from dataclasses import dataclass

from agents.base import Agent

_HEADING_LINE = re.compile(r"^#{1,6}\s")

# Recursive/hybrid is recommended once a document is long enough that no
# single simple strategy is likely to hold up across its whole length --
# not a precise threshold, just a real, stated one.
_LARGE_DOCUMENT_CHARS = 20_000


@dataclass
class _DocumentStats:
    char_count: int
    heading_count: int
    table_line_ratio: float
    paragraph_count: int


def _gather_stats(text: str) -> _DocumentStats:
    lines = text.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    heading_count = sum(1 for line in lines if _HEADING_LINE.match(line))
    table_line_count = sum(
        1 for line in lines if line.strip().startswith("|") and line.strip().endswith("|")
    )
    paragraphs = [block for block in text.split("\n\n") if block.strip()]
    return _DocumentStats(
        char_count=len(text),
        heading_count=heading_count,
        table_line_ratio=(table_line_count / len(non_empty_lines)) if non_empty_lines else 0.0,
        paragraph_count=len(paragraphs),
    )


def _score_table_aware(stats: _DocumentStats) -> float:
    # Even a genuinely table-heavy document rarely has more than ~25% of
    # its lines as table rows (headers/prose surround every table) --
    # scaled so that ratio reaches 1.0 well before 100% would be needed.
    return min(stats.table_line_ratio * 4, 1.0)


def _score_markdown_heading(stats: _DocumentStats) -> float:
    return min(stats.heading_count / 5, 1.0)


def _score_sentence_paragraph(stats: _DocumentStats) -> float:
    # A document that's mostly prose with real paragraph breaks fits
    # this strategy well -- but if it also has substantial heading
    # structure, markdown_heading is the better fit for the same
    # content, so this is capped low in that case rather than competing
    # on equal footing.
    if stats.heading_count >= 3:
        return 0.3
    return min(stats.paragraph_count / 6, 1.0)


def _score_fixed_size(_stats: _DocumentStats) -> float:
    # Always a valid fallback for any document -- flat, low-priority
    # baseline so it only wins when nothing else has real signal.
    return 0.2


def _score_recursive_hybrid(
    stats: _DocumentStats, table_score: float, heading_score: float
) -> float:
    # Takes the already-computed table/heading scores rather than
    # re-deriving its own independent signal, deliberately: an earlier
    # version scored this from raw stats alone and could only ever tie
    # a single-strategy score at the shared 1.0 ceiling, never actually
    # beat it -- caught by testing a genuinely mixed document and seeing
    # table_aware win the tie-break instead of recursive_hybrid, which
    # defeats the point of having a hybrid strategy at all. Recommended
    # specifically when a document needs BOTH table-aware and heading-
    # aware handling at once (scored to exceed whichever single score is
    # highest in that case, not just match it), or when it's long enough
    # that no single simple strategy likely holds up across its whole
    # length.
    if table_score > 0.5 and heading_score > 0.5:
        return min(max(table_score, heading_score) + 0.15, 1.0)
    if stats.char_count > _LARGE_DOCUMENT_CHARS and (table_score > 0.3 or heading_score > 0.3):
        return min(max(table_score, heading_score) + 0.1, 1.0)
    return 0.0


# Deterministic tie-break order, same reasoning as document_analysis.py's
# _CATEGORY_ORDER -- not relying on dict-iteration-order matching
# insertion order implicitly for a decision this visible. Public (not
# underscore-prefixed) since step 103's override endpoint validates a
# caller-supplied strategy name against this same tuple -- one source
# of truth for "what counts as a real strategy name," not duplicated.
STRATEGY_NAMES = (
    "fixed_size",
    "sentence_paragraph",
    "markdown_heading",
    "table_aware",
    "recursive_hybrid",
)

_REASONS: dict[str, str] = {
    "fixed_size": "no strong heading, table, or paragraph structure was detected",
    "sentence_paragraph": "the document has clear paragraph breaks and little heading structure",
    "markdown_heading": "the document has multiple headings giving it clear section structure",
    "table_aware": "a substantial share of the document's lines are table rows",
    "recursive_hybrid": "the document mixes multiple strong structural signals or is very long",
}


@dataclass
class ChunkingRecommendation:
    strategy: str
    scores: dict[str, float]
    reasoning: str


class ChunkingRecommendationAgent(Agent):
    name = "chunking_recommendation"

    def recommend(self, text: str) -> ChunkingRecommendation:
        stats = _gather_stats(text)
        table_score = _score_table_aware(stats)
        heading_score = _score_markdown_heading(stats)
        scores = {
            "fixed_size": _score_fixed_size(stats),
            "sentence_paragraph": _score_sentence_paragraph(stats),
            "markdown_heading": heading_score,
            "table_aware": table_score,
            "recursive_hybrid": _score_recursive_hybrid(stats, table_score, heading_score),
        }

        # >=, not > -- recursive_hybrid's own score is capped at 1.0 like
        # every other strategy's, so its "beat the max of table/heading"
        # bonus (_score_recursive_hybrid above) gets clipped away right
        # when it matters most: a genuinely mixed document where both
        # underlying scores are already near the ceiling. STRATEGY_NAMES
        # deliberately lists recursive_hybrid last so it wins exactly
        # that tie -- a tie against the strategies it was built to beat
        # is itself the signal that the hybrid approach is warranted.
        best_strategy = STRATEGY_NAMES[0]
        for name in STRATEGY_NAMES:
            if scores[name] >= scores[best_strategy]:
                best_strategy = name

        reasoning = (
            f"Recommended '{best_strategy}' (score {scores[best_strategy]:.2f}): "
            f"{_REASONS[best_strategy]}."
        )
        return ChunkingRecommendation(strategy=best_strategy, scores=scores, reasoning=reasoning)
