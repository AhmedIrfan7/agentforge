"""Virus/malware scanning via clamd (ClamAV's daemon), roadmap step 087.

Runs synchronously inside the upload request itself, not as a background
task -- Celery/task-queue infrastructure doesn't exist until step 089, so
this is the only place in the pipeline that can reject an infected file
before it's ever written to storage. Called from
routers/document.py:upload_document right after validate_upload, before
storage.upload_file.

Speaks clamd's INSTREAM protocol directly over a raw asyncio socket
rather than depending on a client library: the protocol is small and has
been stable for over a decade (docs.clamav.net/manual/Usage/
ClamdProtocol.html), and the only async client on PyPI (aioclamd) has had
a single release, from 2022, with no maintenance since -- not something
worth depending on for this.

Protocol: send b"zINSTREAM\0", then the payload as
<4-byte big-endian length><chunk> frames, terminated by a zero-length
chunk. clamd replies with one NUL-terminated line: "stream: OK",
"stream: <signature name> FOUND", or "stream: <message> ERROR". The "z"
prefix (vs "n") is what makes both the command and the reply
NUL-terminated rather than newline-terminated.

clamd's TCP socket has no auth (documented, not an oversight -- see
docs.clamav.net/manual/Usage/Scanning.html), so it must stay reachable
only from the app's own network (docker-compose's default bridge network
locally, an internal-only network in production), never exposed
publicly.
"""

import struct

import anyio

from config import settings
from errors import InfectedFileError

_CHUNK_SIZE = 1024 * 1024  # 1 MB per frame, matches validation.py's read chunk size
_CONNECT_TIMEOUT_SECONDS = 10
_SCAN_TIMEOUT_SECONDS = 60


async def scan_for_viruses(content: bytes) -> None:
    """Raises InfectedFileError if clamd flags the content. Connection
    failures, timeouts, and clamd-side errors (e.g. its own size limit)
    are left to propagate as-is -- an unreachable scanner is an
    infrastructure problem, not something to silently let an upload
    bypass, and the generic exception handler in errors.py already logs
    and reports it correctly without a bespoke AppError subclass, the
    same way storage.py's ClientError isn't wrapped either."""
    with anyio.fail_after(_CONNECT_TIMEOUT_SECONDS):
        stream = await anyio.connect_tcp(settings.clamav_host, settings.clamav_port)

    async with stream:
        await stream.send(b"zINSTREAM\0")
        for offset in range(0, len(content), _CHUNK_SIZE):
            chunk = content[offset : offset + _CHUNK_SIZE]
            await stream.send(struct.pack("!L", len(chunk)) + chunk)
        await stream.send(struct.pack("!L", 0))

        response = b""
        with anyio.fail_after(_SCAN_TIMEOUT_SECONDS):
            while not response.endswith(b"\0"):
                response += await stream.receive(4096)

    result = response.rstrip(b"\0").decode("utf-8", errors="replace")
    if result.endswith("FOUND"):
        signature = result.removeprefix("stream: ").removesuffix(" FOUND")
        raise InfectedFileError(f"File failed a virus scan (detected: {signature}).")
    if result.endswith("ERROR"):
        raise RuntimeError(f"clamd returned an error: {result}")
