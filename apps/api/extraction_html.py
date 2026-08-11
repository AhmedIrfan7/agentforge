"""HTML extraction (roadmap step 093) -- registered into
extraction.py:HANDLERS under "html".

markdownify (MIT), not html2text -- html2text is GPL-3.0-or-later, the
same license-incompatibility reasoning that ruled out PyMuPDF/fitz for
PDF (extraction_pdf.py), checked via PyPI before writing any code
against either. markdownify already depends on beautifulsoup4 (MIT),
which this module also uses directly for the cleanup pass below.

markdownify's own strip= option does NOT remove a tag's content --
verified live -- it only skips wrapping that tag's own text in markdown
syntax, so an unwanted <nav>/<footer> section's text still leaks
straight into the output. <script>/<style> content IS excluded
automatically (they hold no visible text markdownify would emit), but
<nav>/<header>/<footer>/<aside> are not -- real HTML5 structural noise
that's still content-shaped as far as the converter is concerned. Those
are removed outright with BeautifulSoup's .decompose() before
conversion, not markdownify's strip= -- an honest, bounded cleanup
based on unambiguous HTML5 semantics, not an attempt at full "guess the
article body" content extraction (what tools like Readability/
trafilatura do -- a different, much harder problem this step doesn't
take on).

heading_style="ATX" ("# "/"## ") matches every other extractor in this
pipeline. table_infer_header=True treats a table's first row as the
header even without <th> tags -- verified live that the default
(False) produces a broken table (empty header row, duplicated first
row) for the common real-world case of a table using plain <td> for
its header row too.
"""

from bs4 import BeautifulSoup
from markdownify import markdownify

_STRUCTURAL_NOISE_TAGS = ("nav", "header", "footer", "aside", "script", "style")


def extract_html(content: bytes) -> str:
    soup = BeautifulSoup(content.decode("utf-8"), "html.parser")
    for tag in soup.find_all(_STRUCTURAL_NOISE_TAGS):
        tag.decompose()
    return str(markdownify(str(soup), heading_style="ATX", table_infer_header=True)).strip()
