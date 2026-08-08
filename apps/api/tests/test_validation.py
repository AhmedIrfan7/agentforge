"""Pure unit tests for validation.py (roadmap steps 085 file-type,
086 size limit) — no HTTP/DB needed, so the extension x content-type
matrix and chunked-read edge cases are covered directly here rather than
through the much slower real-upload path every case would otherwise
need (org/workspace/knowledge base/auth per case).
tests/test_document_endpoints.py separately proves the endpoint actually
wires these in, not just that the functions are correct in isolation.
"""

import io

import pytest
from fastapi import UploadFile

from errors import FileTooLargeError, UnsupportedFileTypeError
from validation import read_upload_content, validate_upload

# Minimal bytes real enough to trip filetype's actual signature check —
# not full, parseable documents, just their magic-byte headers.
_REAL_PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


def test_disallowed_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload("malware.exe", b"anything")


def test_no_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload("no_extension_at_all", b"anything")


def test_no_filename_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload(None, b"anything")


def test_real_pdf_signature_with_pdf_extension_is_accepted() -> None:
    validate_upload("report.pdf", _REAL_PDF_HEADER)  # does not raise


def test_plain_text_disguised_as_pdf_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload("fake.pdf", b"This is just plain text, not a real PDF.")


def test_valid_utf8_text_with_txt_extension_is_accepted() -> None:
    validate_upload("notes.txt", "Hello, world! Unicode too: café.".encode())  # does not raise


def test_valid_json_content_with_json_extension_is_accepted() -> None:
    validate_upload("data.json", b'{"key": "value"}')  # does not raise


def test_non_utf8_bytes_with_txt_extension_is_rejected() -> None:
    # A lone continuation byte is never valid UTF-8 on its own.
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload("renamed_binary.txt", b"\xff\xfe\x00\x01\x02\x80")


def test_extension_is_case_insensitive() -> None:
    validate_upload("REPORT.PDF", _REAL_PDF_HEADER)  # does not raise


@pytest.mark.anyio
async def test_read_upload_content_within_limit_returns_full_content() -> None:
    data = b"a" * 100
    upload = UploadFile(io.BytesIO(data), filename="small.txt")
    result = await read_upload_content(upload, max_bytes=1000)
    assert result == data


@pytest.mark.anyio
async def test_read_upload_content_over_limit_raises() -> None:
    data = b"a" * 100
    upload = UploadFile(io.BytesIO(data), filename="big.txt")
    with pytest.raises(FileTooLargeError):
        await read_upload_content(upload, max_bytes=50)


@pytest.mark.anyio
async def test_read_upload_content_exactly_at_limit_is_accepted() -> None:
    data = b"a" * 100
    upload = UploadFile(io.BytesIO(data), filename="exact.txt")
    result = await read_upload_content(upload, max_bytes=100)
    assert result == data


@pytest.mark.anyio
async def test_read_upload_content_spanning_multiple_chunks_reconstructs_correctly() -> None:
    # Bigger than validation.py's internal 1 MB chunk size, so this
    # exercises the actual multi-read loop, not just a single read().
    data = bytes(range(256)) * 10_000  # ~2.5 MB
    upload = UploadFile(io.BytesIO(data), filename="multi_chunk.bin")
    result = await read_upload_content(upload, max_bytes=len(data))
    assert result == data
