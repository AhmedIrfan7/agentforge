"""Document quality checks (roadmap step 096) -- informational signals
computed alongside content/metadata extraction, not upload-blocking
validation (that's validation.py's job, at upload time, before a file
is ever stored). These run AFTER extraction succeeds, on content that's
already been accepted -- the question here isn't "should this file be
rejected" but "is something worth flagging about what came out of it."

content_hash: SHA-256 of the raw uploaded bytes -- not the extracted
text, since two files that are byte-identical are unambiguously the
same upload regardless of what extraction does with them, while two
files that merely extract to the same text (e.g. a .txt and a .md with
identical content) are a fuzzier kind of "duplicate" this step doesn't
attempt to detect. Stored on Document.content_hash (indexed) for step
117 ("duplicate-document detection within a knowledge base") to query
against -- this step only computes and stores the signal, it doesn't
act on it (no rejection, no warning surfaced to the caller yet).

is_empty: extracted_text is empty or whitespace-only after stripping.
Deliberately whole-document, not literally per-PAGE despite the roadmap
line's wording ("empty pages") -- none of this pipeline's extractors
(extraction_pdf.py, extraction_docx.py, etc.) currently return a
per-page/per-slide/per-sheet breakdown, only one combined string per
document, so there's nothing to check page-by-page without first
changing what every extractor returns. Reporting a whole-document
emptiness signal honestly is better than claiming page-level detection
this code doesn't actually do.

has_broken_formatting: True when Unicode replacement characters (U+FFFD
-- what a wrong-encoding decode produces) or non-whitespace control
characters make up more than _BROKEN_RATIO_THRESHOLD of the text, and
the text is long enough (_MIN_LENGTH_FOR_BROKEN_CHECK) that a couple of
stray characters in a short string don't trip it by ratio alone. Real,
checkable signal for "something went wrong turning this into text," not
a guess about document quality in some broader sense.
"""

import hashlib
import unicodedata
from dataclasses import dataclass

_BROKEN_RATIO_THRESHOLD = 0.05
_MIN_LENGTH_FOR_BROKEN_CHECK = 20


def compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def is_content_empty(extracted_text: str) -> bool:
    return not extracted_text.strip()


def has_broken_formatting(extracted_text: str) -> bool:
    if len(extracted_text) < _MIN_LENGTH_FOR_BROKEN_CHECK:
        return False
    bad_chars = sum(
        1
        for c in extracted_text
        if c == "�" or (unicodedata.category(c) == "Cc" and c not in "\n\t\r")
    )
    return (bad_chars / len(extracted_text)) > _BROKEN_RATIO_THRESHOLD


@dataclass
class QualityReport:
    content_hash: str
    is_empty: bool
    has_broken_formatting: bool


def assess_quality(content: bytes, extracted_text: str) -> QualityReport:
    return QualityReport(
        content_hash=compute_content_hash(content),
        is_empty=is_content_empty(extracted_text),
        has_broken_formatting=has_broken_formatting(extracted_text),
    )
