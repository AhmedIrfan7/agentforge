"""Upload validation (roadmap step 085: file-type allow-list).

Two layers, because a filename extension alone is trivially spoofable
(rename evil.exe to evil.pdf) and a client-supplied Content-Type header
is exactly as spoofable (the client sets whatever it wants) -- neither
is proof of what a file actually is, only what it claims to be:

1. Every extension must be in ALLOWED_EXTENSIONS -- the roadmap's own
   list, and the primary signal for "what kind of document is this."
2. Where a real binary signature exists (pdf/docx/pptx/xlsx), the
   file's actual bytes are inspected (filetype -- pure-Python magic-byte
   detection, no system libmagic dependency to break across dev
   machines) and must match the claimed extension. Plain-text formats
   (csv/txt/md/html/json/xml) have no magic bytes to check -- there's no
   binary signature for "this is text" -- so the check there is that the
   content actually decodes as UTF-8, which at least catches a renamed
   binary without pretending to verify more than that. A full content or
   malware scan is step 087, not this one.
"""

import filetype

from errors import UnsupportedFileTypeError

ALLOWED_EXTENSIONS = frozenset(
    {"pdf", "docx", "pptx", "xlsx", "csv", "txt", "md", "html", "json", "xml"}
)

_TEXT_EXTENSIONS = frozenset({"csv", "txt", "md", "html", "json", "xml"})

# filetype's own detected-type names for the extensions it can actually
# sniff a binary signature for -- matches ALLOWED_EXTENSIONS' spelling
# exactly for these four; everything else is a _TEXT_EXTENSIONS member
# and falls through to the decodability check instead.
_SIGNATURE_EXTENSIONS = frozenset({"pdf", "docx", "pptx", "xlsx"})


def validate_upload(filename: str | None, content: bytes) -> None:
    extension = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"'.{extension}' is not an allowed file type. Allowed types: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    if extension in _SIGNATURE_EXTENSIONS:
        detected = filetype.guess(content)
        if detected is None or detected.extension != extension:
            raise UnsupportedFileTypeError(
                f"File content doesn't match its '.{extension}' extension."
            )
    else:
        assert extension in _TEXT_EXTENSIONS  # every allowed extension is one or the other
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedFileTypeError(
                f"File content isn't valid text for a '.{extension}' file."
            ) from exc
