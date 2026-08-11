"""Shared table -> markdown conversion (roadmap step 091, promoted out of
extraction_pdf.py in step 092 once docx/pptx/xlsx extraction needed the
identical logic -- one real, non-speculative reason to factor it out,
not a premature abstraction).

Every extractor in this pipeline (pdf, docx, pptx, xlsx so far) produces
markdown output, matching extraction_pdf.py's own reasoning: it's the
shared format step 093 (HTML/Markdown extraction) and step 100
(markdown/heading-aware chunker) are both built around, so every
extractor's tables should render the same way rather than each
inventing its own table syntax.
"""

from collections.abc import Sequence


def rows_to_markdown(rows: Sequence[Sequence[object]]) -> str:
    if not rows:
        return ""
    # None means "empty cell" -> "" -- but a real falsy VALUE (0, False,
    # "") is not the same thing and must still render as itself. `cell
    # or ""` would silently blank those out too; xlsx cells (step 092)
    # actually hit this case, unlike pdf's table cells, which are always
    # text already.
    cleaned = [
        [("" if cell is None else str(cell)).replace("\n", " ").strip() for cell in row]
        for row in rows
    ]
    header, *body = cleaned
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)
