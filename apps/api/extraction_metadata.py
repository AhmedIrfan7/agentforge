"""Metadata extraction (roadmap step 094) -- title/author/dates/language,
stored in Document.doc_metadata (JSONB, present since step 083, empty
until now).

Per-format metadata (title/author/created_at/modified_at/declared
language, where the format has any) lives next to each format's
content-extraction function, in extraction_docx.py/extraction_pptx.py/
extraction_xlsx.py/extraction_pdf.py/extraction_html.py -- METADATA_
HANDLERS below is the registry tying extension to function, same shape
as extraction.py:HANDLERS. csv/txt/json/xml/md have no embedded-
metadata concept at all (no format-level "author" field exists for a
CSV), so they're simply absent from this registry rather than each
returning an empty dict for the same reason -- language detection
(below) still applies to them since it works from the extracted text
itself, not any format-specific source.

language: an explicitly declared one (docx/pptx core_properties.
language, xlsx workbook.properties.language, html's <html lang>) is
trusted over statistical detection when present -- an author's own
declaration is more authoritative than a guess. Falls back to
py3langid, a real language-identification model, only when nothing was
declared. py3langid's norm_probs=True classifier returns a genuine
normalized confidence (0-1) -- verified live that empty/garbage/
single-character input all converge to the same low ~0.17 "I don't
really know" value while real text scores at or near 1.0, which is
what makes a confidence threshold meaningful here rather than
arbitrary. Below _LANGUAGE_CONFIDENCE_THRESHOLD, language is left None
rather than guessing -- a wrong language tag is worse than no tag for
whatever eventually reads doc_metadata.

Each extract_*_metadata function returns whatever raw strings the
underlying library gives -- including empty strings and library-default
sentinel values (python-docx defaults an unset author to the literal
string "python-docx"; openpyxl defaults an unset creator to "openpyxl";
neither is a real person's name). Cleaning that up is centralized here
in build_doc_metadata, not duplicated per format: strip blank strings
to None, and filter the two known author sentinels specifically (no
equivalent sentinel was found for title). Dates are NOT filtered the
same way -- python-docx/python-pptx default an unset created date to a
fixed 2013 timestamp, openpyxl defaults it to whatever moment the
workbook object happened to be constructed, and distinguishing "the
file's real metadata" from "the library's default" reliably isn't
practical the way a literal sentinel string is; this is a known,
accepted limitation of trusting embedded document metadata in general,
not specific to this code.
"""

from collections.abc import Callable

from py3langid.langid import MODEL_FILE, LanguageIdentifier

from extraction_docx import extract_docx_metadata
from extraction_html import extract_html_metadata
from extraction_pdf import extract_pdf_metadata
from extraction_pptx import extract_pptx_metadata
from extraction_xlsx import extract_xlsx_metadata

_LANGUAGE_CONFIDENCE_THRESHOLD = 0.5

# Values these libraries hand back for an author/creator field that was
# never actually set -- verified live against real generated files, not
# assumed from documentation.
_AUTHOR_SENTINELS = frozenset({"python-docx", "openpyxl"})

_identifier = LanguageIdentifier.from_pickled_model(MODEL_FILE, norm_probs=True)

MetadataHandler = Callable[[bytes], dict[str, object]]

METADATA_HANDLERS: dict[str, MetadataHandler] = {
    "docx": extract_docx_metadata,
    "pptx": extract_pptx_metadata,
    "xlsx": extract_xlsx_metadata,
    "pdf": extract_pdf_metadata,
    "html": extract_html_metadata,
}


def normalize_language_code(code: str) -> str:
    # "en-US"/"en_US" -> "en" -- matches py3langid's own ISO 639-1
    # two-letter output, so a declared and a detected language compare
    # on the same footing.
    return code.replace("_", "-").split("-")[0].lower()


def detect_language(text: str) -> str | None:
    if not text.strip():
        return None
    code, confidence = _identifier.classify(text)
    if confidence < _LANGUAGE_CONFIDENCE_THRESHOLD:
        return None
    return normalize_language_code(str(code))


def _clean_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def build_doc_metadata(extension: str, content: bytes, extracted_text: str) -> dict[str, object]:
    handler = METADATA_HANDLERS.get(extension)
    raw: dict[str, object] = handler(content) if handler is not None else {}

    author = _clean_str(raw.get("author"))
    declared_language = _clean_str(raw.get("language"))

    return {
        "title": _clean_str(raw.get("title")),
        "author": None if author in _AUTHOR_SENTINELS else author,
        "created_at": _clean_str(raw.get("created_at")),
        "modified_at": _clean_str(raw.get("modified_at")),
        "language": (
            normalize_language_code(declared_language)
            if declared_language
            else detect_language(extracted_text)
        ),
    }
