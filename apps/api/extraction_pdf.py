"""PDF text/structure extraction (roadmap step 091) -- registered into
extraction.py:HANDLERS under "pdf".

pdfplumber (MIT -- deliberately not PyMuPDF/fitz, which is AGPL-3.0 or
commercial-licensed; this project is Apache 2.0, and AGPL's copyleft
terms are a real incompatibility for an open-source SaaS product, not
just a preference).

Output is markdown: "# "/"## " for detected headings, pipe-table syntax
for detected tables -- not an arbitrary choice, it's what step 100
("markdown/heading-aware chunker") will consume, and what step 093
(HTML/Markdown extraction) will also produce, giving every extractor a
shared downstream format rather than each inventing its own.

pdfplumber has no built-in "this is a heading" concept (no PDF format
does -- headings are a visual/stylistic convention, not structured
data), so this uses a font-size heuristic: extract_words(extra_attrs=
["size"]) gives each word's rendered size; a line whose size is
noticeably larger than the page's dominant (body-text) size is treated
as a heading. This is a real, common, honest technique (not an ML
model, doesn't claim to be one) -- verified against a real generated
PDF (headings at 18pt/14pt over 10pt body text) before being trusted,
same "confirm the real library shape before writing code against it"
discipline as every other new dependency this project has added.

Table cells also show up in extract_words() as ordinary words -- a
naive line-by-line text extraction would print a table's contents twice
(once mangled as loose words, once as the actual table). Words falling
inside a detected table's bounding box are excluded from line
extraction for exactly this reason; tables and lines are then
interleaved back together by vertical position so the output reads in
the same order as the original page, not "all text, then all tables."
"""

import io
from dataclasses import dataclass

import pdfplumber

from extraction_tables import rows_to_markdown

# A line's font size relative to the page's dominant (body-text) size,
# above which it's treated as a heading. Two tiers, not a single cutoff
# -- a document's actual title is usually rendered noticeably larger
# than its section headings, and collapsing both to the same markdown
# level would lose that distinction.
_H1_SIZE_RATIO = 1.5
_H2_SIZE_RATIO = 1.15


@dataclass
class _Line:
    top: float
    text: str
    size: float


def _word_midpoint_in_bbox(word: dict[str, float], bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    mid_x = (word["x0"] + word["x1"]) / 2
    mid_y = (word["top"] + word["bottom"]) / 2
    return x0 <= mid_x <= x1 and top <= mid_y <= bottom


def _group_words_into_lines(words: list[dict[str, float]]) -> list[_Line]:
    # Words on the same visual line have nearly, but not always exactly,
    # equal "top" values -- round to a few-pixel bucket so they group
    # together instead of each forming its own single-word "line".
    buckets: dict[int, list[dict[str, float]]] = {}
    for word in words:
        bucket_key = round(word["top"] / 3) * 3
        buckets.setdefault(bucket_key, []).append(word)

    lines: list[_Line] = []
    for bucket_key in sorted(buckets):
        line_words = sorted(buckets[bucket_key], key=lambda w: w["x0"])
        sizes = sorted(w["size"] for w in line_words)
        lines.append(
            _Line(
                top=bucket_key,
                text=" ".join(str(w["text"]) for w in line_words),
                size=sizes[len(sizes) // 2],  # median, resists one oddly-sized word skewing it
            )
        )
    return lines


def _format_line(line: _Line, body_size: float) -> str:
    if not line.text.strip():
        return ""
    if body_size > 0 and line.size >= body_size * _H1_SIZE_RATIO:
        return f"# {line.text}"
    if body_size > 0 and line.size >= body_size * _H2_SIZE_RATIO:
        return f"## {line.text}"
    return line.text


def extract_pdf(content: bytes) -> str:
    page_texts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        pages_data = []
        all_body_sizes: list[float] = []
        for page in pdf.pages:
            tables = page.find_tables()
            table_bboxes = [t.bbox for t in tables]
            words = page.extract_words(extra_attrs=["size"])
            body_words = [
                w for w in words if not any(_word_midpoint_in_bbox(w, b) for b in table_bboxes)
            ]
            all_body_sizes.extend(w["size"] for w in body_words)
            pages_data.append((body_words, tables))

        body_size = sorted(all_body_sizes)[len(all_body_sizes) // 2] if all_body_sizes else 0.0

        for body_words, tables in pages_data:
            items: list[tuple[float, str]] = [
                (line.top, _format_line(line, body_size))
                for line in _group_words_into_lines(body_words)
            ]
            items.extend((table.bbox[1], rows_to_markdown(table.extract())) for table in tables)
            items.sort(key=lambda item: item[0])
            page_text = "\n\n".join(text for _, text in items if text)
            if page_text:
                page_texts.append(page_text)

    return "\n\n".join(page_texts)
