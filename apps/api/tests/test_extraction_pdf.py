"""Unit tests for extraction_pdf.py (roadmap step 091) -- real PDFs
generated with reportlab (dev-only dependency, used here and nowhere in
application code), not fixture files checked into the repo or fetched
from anywhere -- deterministic, and the exact font sizes reportlab's
built-in styles use (Title=18pt, Heading2=14pt, Normal=10pt) are known
and asserted against directly, the same "confirm the real library shape
before trusting it" approach extraction_pdf.py's own module docstring
describes for pdfplumber itself.
"""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from extraction_pdf import extract_pdf, extract_pdf_metadata

_STYLES = getSampleStyleSheet()


def _build_pdf(story: list[object]) -> bytes:
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter).build(story)
    return buf.getvalue()


def test_plain_paragraph_extracts_as_plain_text() -> None:
    pdf = _build_pdf([Paragraph("Just an ordinary sentence of body text.", _STYLES["Normal"])])
    text = extract_pdf(pdf)
    assert "Just an ordinary sentence of body text." in text
    assert "#" not in text


def test_title_style_becomes_h1() -> None:
    pdf = _build_pdf(
        [
            Paragraph("Document Title", _STYLES["Title"]),
            Paragraph("Some body text underneath the title.", _STYLES["Normal"]),
        ]
    )
    text = extract_pdf(pdf)
    assert "# Document Title" in text
    assert "## Document Title" not in text  # a genuine H1, not H2


def test_heading2_style_becomes_h2_not_h1() -> None:
    pdf = _build_pdf(
        [
            Paragraph("A Section Heading", _STYLES["Heading2"]),
            Paragraph("Body text explaining the section.", _STYLES["Normal"]),
        ]
    )
    lines = extract_pdf(pdf).splitlines()
    assert "## A Section Heading" in lines
    assert "# A Section Heading" not in lines  # a genuine H2, not H1


def test_table_becomes_markdown_pipe_table_without_duplication() -> None:
    table = Table(
        [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]],
        style=TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]),
    )
    pdf = _build_pdf(
        [
            Paragraph("People", _STYLES["Heading2"]),
            table,
            Paragraph("End of doc.", _STYLES["Normal"]),
        ]
    )
    text = extract_pdf(pdf)

    assert "| Name | Age |" in text
    assert "| Alice | 30 |" in text
    assert "| Bob | 25 |" in text
    # Table cell text also shows up in pdfplumber's raw word extraction
    # (see extraction_pdf.py's module docstring) -- must not ALSO appear
    # as loose, unformatted text outside the markdown table.
    assert text.count("Alice") == 1
    assert text.count("Bob") == 1


def test_headings_and_body_stay_in_reading_order() -> None:
    pdf = _build_pdf(
        [
            Paragraph("First Heading", _STYLES["Heading2"]),
            Paragraph("First body.", _STYLES["Normal"]),
            Paragraph("Second Heading", _STYLES["Heading2"]),
            Paragraph("Second body.", _STYLES["Normal"]),
        ]
    )
    text = extract_pdf(pdf)
    assert text.index("First Heading") < text.index("First body.")
    assert text.index("First body.") < text.index("Second Heading")
    assert text.index("Second Heading") < text.index("Second body.")


def test_empty_document_does_not_crash() -> None:
    pdf = _build_pdf([Paragraph("", _STYLES["Normal"])])
    assert isinstance(extract_pdf(pdf), str)


def test_metadata_reads_real_info_dictionary() -> None:
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, title="Explicit PDF Title", author="Real Author").build(
        [Paragraph("Body.", _STYLES["Normal"])]
    )
    metadata = extract_pdf_metadata(buf.getvalue())
    assert metadata["title"] == "Explicit PDF Title"
    assert metadata["author"] == "Real Author"
    # reportlab stamps CreationDate/ModDate with the real build time --
    # just confirm a real ISO 8601 string came back, not reportlab's
    # own "D:..." format leaking through unparsed.
    assert metadata["created_at"] is not None
    assert str(metadata["created_at"]).count("-") >= 2


def test_metadata_with_title_author_unset_returns_reportlabs_raw_default() -> None:
    # Not this project's sentinel to filter -- reportlab is a PDF-
    # generation library used here only to build test fixtures, not a
    # tool real end users author uploaded documents with the way
    # python-docx/openpyxl plausibly are, so "(anonymous)" isn't in
    # extraction_metadata.py's _AUTHOR_SENTINELS. This just documents
    # extract_pdf_metadata's own "raw, uncleaned" contract: whatever the
    # Info dictionary says comes back as-is.
    pdf = _build_pdf([Paragraph("No metadata set.", _STYLES["Normal"])])
    metadata = extract_pdf_metadata(pdf)
    assert metadata["title"] == "(anonymous)"
    assert metadata["author"] == "(anonymous)"
