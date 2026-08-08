"""Unit tests for antivirus.py (roadmap step 087) -- hits a real clamd
(docker-compose.yml's clamav service), same "no mocks for infrastructure
we already run locally/in CI" approach as test_validation.py's sibling
test_document_endpoints.py takes for MinIO.
"""

import pytest

from antivirus import scan_for_viruses
from config import settings
from errors import InfectedFileError

# The official EICAR test file -- a standard, harmless ASCII string every
# antivirus engine (including ClamAV) is guaranteed to flag as a
# "virus," specifically so software like this can be tested without
# needing a real malware sample. See https://www.eicar.org/download-anti-malware-testfile/.
_EICAR_TEST_STRING = (
    r"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
).encode("ascii")


@pytest.mark.anyio
async def test_clean_content_does_not_raise() -> None:
    await scan_for_viruses(b"just an ordinary, harmless file.")  # does not raise


@pytest.mark.anyio
async def test_eicar_test_string_is_flagged_as_infected() -> None:
    with pytest.raises(InfectedFileError) as exc_info:
        await scan_for_viruses(_EICAR_TEST_STRING)
    assert "Eicar" in exc_info.value.message


@pytest.mark.anyio
async def test_empty_content_does_not_raise() -> None:
    await scan_for_viruses(b"")  # does not raise


@pytest.mark.anyio
async def test_unreachable_clamd_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Port 1 is a privileged port nothing is listening on locally --
    # connection refused, fast, no real timeout wait needed.
    monkeypatch.setattr(settings, "clamav_port", 1)
    with pytest.raises(OSError):
        await scan_for_viruses(b"anything")
