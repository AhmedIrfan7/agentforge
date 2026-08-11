"""Document Analysis Agent (roadmap step 095, AGENTS.md SECTION 5) --
classifies a document's type before indexing. Scoped tightly to what the
roadmap line actually asks for ("classifies doc type"), not the full
list AGENTS.md aspirationally describes for this agent (detecting
tables/code/duplicate uploads, etc.) -- table detection is already
inherent to extraction_tables.py's own work (steps 091-093), and
duplicate-upload detection is explicitly its own later roadmap step
(117), not this one's to redo.

Classification is keyword-phrase scoring against the extracted markdown
text, not an ML model or an LLM call -- a real, working, honest
technique for a first skeleton, same "don't overclaim precision"
stance as extraction_pdf.py's font-size heading heuristic and
extraction_metadata.py's language-confidence threshold. Each candidate
type has a list of case-insensitive phrases; whichever type matches the
most phrases wins, ties broken by _CATEGORY_ORDER (deterministic, not
dict-iteration-order-dependent); zero matches across every category
falls back to "general" rather than forcing a confident-looking label
onto content that doesn't fit any of them. matched_keywords reports
exactly which phrases drove the winning classification -- explainable
by construction, not a fabricated confidence score standing in for one.
"""

from dataclasses import dataclass, field

from agents.base import Agent

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "faq": (
        "frequently asked questions",
        "faq",
    ),
    "manual": (
        "table of contents",
        "getting started",
        "installation guide",
        "troubleshooting",
        "user manual",
        "user guide",
        "step-by-step",
        "quick start",
    ),
    "legal": (
        "whereas",
        "hereinafter",
        "the parties agree",
        "governing law",
        "indemnify",
        "in witness whereof",
        "terms and conditions",
        "shall not be liable",
        "this agreement",
    ),
    "academic": (
        "abstract",
        "references",
        "bibliography",
        "et al.",
        "methodology",
        "literature review",
    ),
    "business": (
        "executive summary",
        "quarterly report",
        "revenue",
        "stakeholder",
        "return on investment",
        "invoice",
        "proposal",
        "budget forecast",
    ),
}

# Deterministic tie-break order -- dict iteration order happens to match
# insertion order in Python, but relying on that implicitly for a
# decision this visible would be fragile; spelled out on purpose.
_CATEGORY_ORDER = ("faq", "manual", "legal", "academic", "business")

_FALLBACK_TYPE = "general"


@dataclass
class DocumentAnalysisResult:
    document_type: str
    matched_keywords: list[str] = field(default_factory=list)


class DocumentAnalysisAgent(Agent):
    name = "document_analysis"

    def analyze(self, text: str) -> DocumentAnalysisResult:
        lowered = text.lower()
        best_type = _FALLBACK_TYPE
        best_matches: list[str] = []
        for category in _CATEGORY_ORDER:
            matches = [phrase for phrase in _KEYWORDS[category] if phrase in lowered]
            if len(matches) > len(best_matches):
                best_type, best_matches = category, matches
        return DocumentAnalysisResult(document_type=best_type, matched_keywords=best_matches)
