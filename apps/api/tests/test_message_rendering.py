"""Unit tests for message_rendering.py (roadmap step 185). Pure
function tests, no DB needed.
"""

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


def test_fenced_code_blocks_are_not_rendered_yet() -> None:
    """Step 186's own job -- no extensions are enabled here, so a
    fenced code block renders as plain markdown-untouched text inside
    a paragraph, not a real <pre><code> block."""
    html = render_markdown("```\nsome code\n```")
    assert "<pre>" not in html


def test_tables_are_not_rendered_yet() -> None:
    """Step 186's own job -- table syntax passes through unrendered."""
    html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<table>" not in html
