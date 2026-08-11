"""Content extraction dispatcher (roadmap step 090) -- the first real
Celery task, routing an uploaded document to a per-file-type extraction
handler by extension, same registry-of-handlers shape as
auth/oauth.py:PROVIDERS (a plain dict, not a decorator-based registration
mechanism -- there's no reason for more machinery than that yet).

HANDLERS covers four plain-text extensions (csv/txt/json/xml) plus
pdf/docx/pptx/xlsx as of step 092. Decoding as UTF-8 -- already-
validated bytes, validate_upload (step 085) already proved every stored
file under the plain-text extensions decodes cleanly -- genuinely IS
the full extraction for those: there's no further structure to pull out
of a CSV/plain-text/JSON/XML file the way there is from a PDF's
headings, a DOCX's styled paragraphs, a PPTX's slides, or an XLSX's
sheets (extraction_pdf.py, extraction_docx.py, extraction_pptx.py,
extraction_xlsx.py -- extraction_tables.py holds the rows-to-markdown
conversion all four table-producing formats share). md is deliberately
NOT here yet -- markdown gets real structure-aware extraction in step
093, not treated as opaque plain text. html/md stay unregistered until
step 093 lands; a document of one of those types lands on
"extraction_unsupported", which is the honest state today, not a bug --
it stops being reachable for each type exactly as its step registers a
real handler here.

dispatch_extraction is dispatched from routers/document.py:upload_document
via .delay() from inside the route body, which runs *before* the
request's own transaction commits (dependencies/tenant.py:get_tenant_db
commits after the route returns) -- so a fast worker can start the task
before the Document row it's looking for is even visible yet. Handled
with a short, bounded retry rather than SQLAlchemy after-commit event
wiring: simpler, and self-healing under any commit-timing scenario, not
just this specific race.
"""

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from celery_app import celery_app
from db import get_worker_session, set_tenant_context
from extraction_docx import extract_docx
from extraction_pdf import extract_pdf
from extraction_pptx import extract_pptx
from extraction_xlsx import extract_xlsx
from repositories.document import DocumentRepository
from storage import download_file
from validation import get_extension

ExtractionHandler = Callable[[bytes], str]


def _extract_plain_text(content: bytes) -> str:
    return content.decode("utf-8")


HANDLERS: dict[str, ExtractionHandler] = {
    "csv": _extract_plain_text,
    "txt": _extract_plain_text,
    "json": _extract_plain_text,
    "xml": _extract_plain_text,
    "pdf": extract_pdf,
    "docx": extract_docx,
    "pptx": extract_pptx,
    "xlsx": extract_xlsx,
}


class _DocumentNotFoundYet(Exception):
    """The dispatched document isn't visible in this transaction yet --
    almost certainly the upload-commit race described in this module's
    docstring, not a real 404 (nothing deletes a Document this early in
    its life). Caught by dispatch_extraction and retried."""


async def _run_extraction(document_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    async with get_worker_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = DocumentRepository(session, tenant_id)
        document = await repo.get(document_id)
        if document is None:
            raise _DocumentNotFoundYet(str(document_id))

        handler = HANDLERS.get(get_extension(document.title))
        if handler is None:
            document.status = "extraction_unsupported"
            await session.commit()
            return

        document.status = "processing"
        await session.commit()
        # SET LOCAL only lasts one transaction (db.py:set_tenant_context's
        # own docstring, and the exact bug class step 074 found live) --
        # the commit above ended it, so it must be set again before the
        # next write in this same session.
        await set_tenant_context(session, tenant_id)

        content = await download_file(document.storage_key)
        try:
            extracted_text = handler(content)
        except Exception:
            document.status = "extraction_failed"
            await session.commit()
            raise

        document.status = "extracted"
        document.extracted_text = extracted_text
        await session.commit()


@celery_app.task(bind=True, name="dispatch_extraction", max_retries=5)  # type: ignore[untyped-decorator]
def dispatch_extraction(self: Any, document_id: str, tenant_id: str) -> None:
    try:
        asyncio.run(_run_extraction(uuid.UUID(document_id), uuid.UUID(tenant_id)))
    except _DocumentNotFoundYet as exc:
        raise self.retry(countdown=1, exc=exc) from exc
