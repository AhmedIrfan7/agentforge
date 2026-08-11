"""Unit tests for quality.py (roadmap step 096)."""

import hashlib

from quality import assess_quality, compute_content_hash, has_broken_formatting, is_content_empty


def test_content_hash_matches_real_sha256() -> None:
    content = b"some real file bytes"
    assert compute_content_hash(content) == hashlib.sha256(content).hexdigest()


def test_content_hash_differs_for_different_bytes() -> None:
    assert compute_content_hash(b"one") != compute_content_hash(b"two")


def test_content_hash_is_identical_for_identical_bytes() -> None:
    assert compute_content_hash(b"same") == compute_content_hash(b"same")


def test_empty_text_is_empty() -> None:
    assert is_content_empty("") is True
    assert is_content_empty("   \n\t  ") is True


def test_real_text_is_not_empty() -> None:
    assert is_content_empty("Real content here.") is False


def test_clean_text_is_not_broken() -> None:
    text = "This is a perfectly ordinary sentence of real, clean English text."
    assert has_broken_formatting(text) is False


def test_mostly_replacement_characters_is_broken() -> None:
    text = "Some text �������� with garbage mixed in badly"
    assert has_broken_formatting(text) is True


def test_short_text_with_one_bad_char_is_not_flagged() -> None:
    # Below _MIN_LENGTH_FOR_BROKEN_CHECK -- a single stray character in a
    # short string shouldn't trip the ratio check just because the
    # denominator is small.
    assert has_broken_formatting("ok�") is False


def test_assess_quality_combines_all_three_signals() -> None:
    content = b"raw file bytes"
    report = assess_quality(content, "Real extracted text content here.")
    assert report.content_hash == compute_content_hash(content)
    assert report.is_empty is False
    assert report.has_broken_formatting is False


def test_assess_quality_flags_empty_extraction() -> None:
    report = assess_quality(b"some real file bytes that produced nothing", "")
    assert report.is_empty is True
