"""Unit tests for extraction_html.py (roadmap step 093) -- real HTML
strings, no fixture-generation library needed since HTML is authored
directly as text.
"""

from extraction_html import extract_html, extract_html_metadata


def test_plain_paragraph_extracts_as_plain_text() -> None:
    html = b"<p>Just an ordinary sentence of body text.</p>"
    assert extract_html(html) == "Just an ordinary sentence of body text."


def test_h1_becomes_markdown_h1() -> None:
    html = b"<h1>Main Title</h1><p>Body text.</p>"
    text = extract_html(html)
    assert "# Main Title" in text
    assert "## Main Title" not in text


def test_h2_becomes_markdown_h2_not_h1() -> None:
    html = b"<h2>A Section Heading</h2><p>Body text.</p>"
    lines = extract_html(html).splitlines()
    assert "## A Section Heading" in lines
    assert "# A Section Heading" not in lines


def test_table_becomes_markdown_pipe_table_with_or_without_th() -> None:
    html_with_th = (
        b"<table><tr><th>Name</th><th>Age</th></tr><tr><td>Alice</td><td>30</td></tr></table>"
    )
    text = extract_html(html_with_th)
    assert "| Name | Age |" in text
    assert "| Alice | 30 |" in text

    # Real-world HTML very often uses a plain <td> row for the header
    # too -- table_infer_header=True is what keeps this from producing
    # a broken table (verified live before trusting the default).
    html_without_th = (
        b"<table><tr><td>Name</td><td>Age</td></tr><tr><td>Bob</td><td>25</td></tr></table>"
    )
    text2 = extract_html(html_without_th)
    assert "| Name | Age |" in text2
    assert "| Bob | 25 |" in text2
    assert text2.count("Name") == 1  # not duplicated into its own header row


def test_script_and_style_content_is_excluded() -> None:
    html = (
        b"<html><head><style>body { color: red; }</style>"
        b'<script>alert("hi");</script></head>'
        b"<body><p>Real content.</p></body></html>"
    )
    text = extract_html(html)
    assert "Real content." in text
    assert "color: red" not in text
    assert "alert" not in text


def test_nav_header_footer_aside_content_is_excluded() -> None:
    # markdownify's own strip= option does NOT remove a tag's content,
    # only its markdown formatting -- verified live. These four tags are
    # decomposed outright before conversion instead.
    html = (
        b"<nav>Home | About</nav>"
        b"<header>Site Header</header>"
        b"<h1>Main Title</h1>"
        b"<p>Real body content.</p>"
        b"<aside>Related links</aside>"
        b"<footer>Copyright 2026</footer>"
    )
    text = extract_html(html)
    assert "Real body content." in text
    assert "Home | About" not in text
    assert "Site Header" not in text
    assert "Related links" not in text
    assert "Copyright 2026" not in text


def test_empty_html_does_not_crash() -> None:
    assert isinstance(extract_html(b""), str)


def test_metadata_reads_title_meta_author_and_lang_attribute() -> None:
    html = (
        b'<html lang="fr-FR"><head><title>Explicit Page Title</title>'
        b'<meta name="author" content="Real Web Author">'
        b'<meta name="date" content="2026-05-01">'
        b"</head><body><p>content</p></body></html>"
    )
    metadata = extract_html_metadata(html)
    assert metadata["title"] == "Explicit Page Title"
    assert metadata["author"] == "Real Web Author"
    assert metadata["created_at"] == "2026-05-01"
    assert metadata["language"] == "fr-FR"


def test_metadata_with_no_head_returns_all_none() -> None:
    metadata = extract_html_metadata(b"<body><p>just body content</p></body>")
    assert metadata["title"] is None
    assert metadata["author"] is None
    assert metadata["created_at"] is None
    assert metadata["language"] is None
