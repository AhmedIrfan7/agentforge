"""Unit tests for extraction_xlsx.py (roadmap step 092) -- real .xlsx
files built with openpyxl itself.
"""

import io
from collections.abc import Callable

import openpyxl
from openpyxl import Workbook

from extraction_xlsx import extract_xlsx, extract_xlsx_metadata


def _build_xlsx(build: Callable[[Workbook], None]) -> bytes:
    workbook = openpyxl.Workbook()
    build(workbook)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def test_single_sheet_becomes_heading_plus_table() -> None:
    def build(wb: Workbook) -> None:
        ws = wb.active
        assert ws is not None
        ws.title = "Summary"
        ws.append(["Name", "Age"])
        ws.append(["Alice", 30])

    text = extract_xlsx(_build_xlsx(build))
    assert "# Summary" in text
    assert "| Name | Age |" in text
    assert "| Alice | 30 |" in text


def test_multiple_sheets_both_appear_in_workbook_order() -> None:
    def build(wb: Workbook) -> None:
        ws1 = wb.active
        assert ws1 is not None
        ws1.title = "First"
        ws1.append(["a"])
        wb.create_sheet("Second").append(["b"])

    text = extract_xlsx(_build_xlsx(build))
    assert text.index("# First") < text.index("# Second")


def test_zero_and_false_cell_values_are_not_blanked_out() -> None:
    # rows_to_markdown must distinguish None ("empty cell") from a real
    # falsy VALUE -- `cell or ""` would silently blank both 0 and False
    # the same way it blanks a genuinely empty cell, which is wrong for
    # xlsx specifically: its cells are real typed values, not always
    # strings, unlike every other extractor's table cells so far.
    def build(wb: Workbook) -> None:
        ws = wb.active
        assert ws is not None
        ws.append(["Metric", "Value"])
        ws.append(["Count", 0])
        ws.append(["Passed", False])
        ws.append(["Note", None])

    text = extract_xlsx(_build_xlsx(build))
    assert "| Count | 0 |" in text
    assert "| Passed | False |" in text
    assert "| Note |  |" in text


def test_empty_workbook_does_not_crash() -> None:
    content = _build_xlsx(lambda wb: None)
    assert isinstance(extract_xlsx(content), str)


def test_metadata_reads_real_workbook_properties() -> None:
    def build(wb: Workbook) -> None:
        wb.properties.title = "Explicit Sheet Title"
        wb.properties.creator = "Real Creator"
        wb.properties.language = "de-DE"

    metadata = extract_xlsx_metadata(_build_xlsx(build))
    assert metadata["title"] == "Explicit Sheet Title"
    # xlsx's own field is `creator`, normalized to a common "author" key.
    assert metadata["author"] == "Real Creator"
    assert metadata["language"] == "de-DE"


def test_metadata_on_a_never_annotated_workbook_reports_library_default_creator() -> None:
    # Raw values, uncleaned -- extraction_metadata.py is what filters
    # the "openpyxl" default-creator sentinel, not this function.
    metadata = extract_xlsx_metadata(_build_xlsx(lambda wb: None))
    assert metadata["author"] == "openpyxl"
