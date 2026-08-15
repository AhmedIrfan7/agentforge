"""Unit tests for message_rendering.py (roadmap steps 185-186). Pure
function tests, no DB needed.
"""

import pytest

from message_rendering import render_markdown


def test_renders_a_heading() -> None:
    assert render_markdown("# Hello") == "<h1>Hello</h1>"


def test_renders_bold_and_italic() -> None:
    html = render_markdown("**bold** and *italic*")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html


def test_renders_an_unordered_list() -> None:
    html = render_markdown("- item1\n- item2")
    assert "<ul>" in html
    assert "<li>item1</li>" in html
    assert "<li>item2</li>" in html


def test_renders_a_link() -> None:
    html = render_markdown("[click here](https://example.com)")
    assert 'href="https://example.com"' in html
    assert ">click here<" in html


def test_plain_text_with_no_markdown_syntax_renders_as_a_paragraph() -> None:
    assert render_markdown("just a plain message") == "<p>just a plain message</p>"


def test_strips_a_raw_script_tag_embedded_in_content() -> None:
    html = render_markdown("Hello <script>alert('xss')</script> world")
    assert "<script>" not in html
    assert "alert" not in html


def test_strips_an_inline_event_handler_attribute() -> None:
    html = render_markdown('<img src="x" onerror="alert(1)">')
    assert "onerror" not in html


def test_renders_a_plain_fenced_code_block() -> None:
    html = render_markdown("```\nprint(1)\n```")
    assert "<pre><code>" in html
    assert "print(1)" in html


def test_renders_a_fenced_code_block_and_preserves_the_language_class() -> None:
    html = render_markdown("```python\nprint(1)\n```")
    assert '<code class="language-python">' in html


def test_renders_a_table() -> None:
    html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<table>" in html
    assert "<th>a</th>" in html
    assert "<td>1</td>" in html


def test_inline_code_gets_no_class_attribute() -> None:
    html = render_markdown("Some text with `inline code` in it")
    assert "<code>inline code</code>" in html
    assert "class=" not in html


def test_the_language_prefix_filter_rejects_a_non_language_class_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real defense in depth, not decorative -- proves the filter
    itself rejects a class value that doesn't start with "language-",
    independent of whether Python-Markdown's own fence parser would
    ever actually produce one (it doesn't, confirmed live in this
    module's own docstring)."""
    monkeypatch.setattr(
        "message_rendering.markdown.markdown",
        lambda content, extensions: '<code class="evil-payload">x</code>',
    )
    html = render_markdown("irrelevant, markdown.markdown is monkeypatched above")
    assert "class=" not in html
