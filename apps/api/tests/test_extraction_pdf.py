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

from extraction_pdf import extract_pdf

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
