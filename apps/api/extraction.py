"""Content extraction dispatcher (roadmap step 090) -- the first real
Celery task, routing an uploaded document to a per-file-type extraction
handler by extension, same registry-of-handlers shape as
auth/oauth.py:PROVIDERS (a plain dict, not a decorator-based registration
mechanism -- there's no reason for more machinery than that yet).

HANDLERS covers all ten allowed extensions (validation.py:
ALLOWED_EXTENSIONS) as of step 093. Five extensions decode as UTF-8 and
stop there -- csv/txt/json/xml (since step 090) and, as of this step,
md too. Earlier docstrings here said markdown would get "real
structure-aware extraction," expecting it to need the same kind of
transformation pdf/docx/pptx/xlsx do; reconsidered once this step
actually arrived: markdown is already this pipeline's own target output
format (every other extractor produces it), so an uploaded .md file's
bytes already ARE the extracted content -- there's nothing to pull out
that isn't already there, the same way there's nothing to pull out of a
CSV. The remaining five formats (pdf, docx, pptx, xlsx, html) need a
real transformation to reach that same markdown shape
(extraction_pdf.py, extraction_docx.py, extraction_pptx.py,
extraction_xlsx.py, extraction_html.py -- extraction_tables.py holds
the rows-to-markdown conversion the four table-producing ones share).
Every allowed extension now has a real handler, so
"extraction_unsupported" is no longer reachable through any upload this
API currently accepts -- it stays defined for the day a new extension
is added to ALLOWED_EXTENSIONS before this dict grows to match, rather
than an upload silently sitting at "processing" forever.

dispatch_extraction is dispatched from routers/document.py:upload_document
via .delay() from inside the route body, which runs *before* the
request's own transaction commits (dependencies/tenant.py:get_tenant_db
commits after the route returns) -- so a fast worker can start the task
before the Document row it's looking for is even visible yet. Handled
with a short, bounded retry rather than SQLAlchemy after-commit event
wiring: simpler, and self-healing under any commit-timing scenario, not
just this specific race.

As of step 094, a successful content extraction also populates
Document.doc_metadata (title/author/created_at/modified_at/language --
extraction_metadata.py:build_doc_metadata) in the same pass, reusing the
same downloaded bytes and extracted text rather than a separate
dispatched task that would need to re-fetch both. A metadata-extraction
failure is treated the same as a content-extraction failure (falls into
the same except block, marks "extraction_failed") -- deliberately not a
separate partial-success state; nothing about this pipeline has needed
that distinction yet, and inventing it now would be solving a problem
that hasn't actually occurred.

As of step 095, the same pass also runs agents/document_analysis.py's
DocumentAnalysisAgent against extracted_text, adding "document_type"
and "document_type_signals" to doc_metadata -- same reasoning as
metadata extraction: it's a real analysis step, not free-standing
product surface, so it belongs in this same task rather than a separate
dispatch that would need to re-fetch content that's already in memory.

As of step 096, the same pass also runs quality.py:assess_quality,
adding "quality": {"is_empty", "has_broken_formatting"} to doc_metadata
and setting Document.content_hash (its own indexed column, not JSONB --
step 117's duplicate-detection lookup needs to query it efficiently).

As of step 097, the same pass also runs agents/chunking_recommendation.py's
ChunkingRecommendationAgent, adding "chunking_recommendation":
{"strategy", "scores", "reasoning"} to doc_metadata -- the full
per-strategy scores stay JSONB diagnostic data, not worth their own
columns. None of the five strategies it recommends among have a real
chunker yet (steps 098-102) -- the recommendation itself is this step's
deliverable.

As of step 104, the recommendation ALSO sets a real default on
Document's own chunking_strategy/chunking_strategy_source (="recommended")
/chunking_strategy_reasoning columns -- unlike the diagnostic scores,
the single chosen strategy is something step 105+ needs to read cheaply
and reliably, not dig out of doc_metadata. routers/document.py's
override endpoint (step 103) updates these same columns to "accepted"/
"override" on an explicit call, comparing against doc_metadata's own
["chunking_recommendation"]["strategy"] (the ORIGINAL recommendation,
which never changes) rather than the current column value (which does,
as overrides happen) -- so overriding a document more than once still
correctly names what was actually recommended, not whatever the
previous decision happened to be.

As of step 108, a successful extraction also dispatches
embeddings_pipeline.py:dispatch_embedding_generation -- the same
"one stage's success kicks off the next" shape upload_document already
uses to start extraction itself. Dispatched only after _run_extraction's
own asyncio.run() returns without raising, i.e. only once
Document.chunking_strategy is genuinely set and committed -- not from
inside _run_extraction itself, so a retried/duplicate extraction attempt
(the _DocumentNotFoundYet path) can't also duplicate-dispatch embedding
generation.
"""

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from agents.chunking_recommendation import ChunkingRecommendationAgent
from agents.document_analysis import DocumentAnalysisAgent
from celery_app import celery_app
from db import get_worker_session, set_tenant_context
from embeddings_pipeline import dispatch_embedding_generation
from extraction_docx import extract_docx
from extraction_html import extract_html
from extraction_metadata import build_doc_metadata
from extraction_pdf import extract_pdf
from extraction_pptx import extract_pptx
from extraction_xlsx import extract_xlsx
from quality import assess_quality
from repositories.document import DocumentRepository
from storage import download_file
from validation import get_extension

ExtractionHandler = Callable[[bytes], str]


def _extract_plain_text(content: bytes) -> str:
    return content.decode("utf-8")


_document_analysis_agent = DocumentAnalysisAgent()
_chunking_recommendation_agent = ChunkingRecommendationAgent()

HANDLERS: dict[str, ExtractionHandler] = {
    "csv": _extract_plain_text,
    "txt": _extract_plain_text,
    "json": _extract_plain_text,
    "xml": _extract_plain_text,
    "md": _extract_plain_text,
    "pdf": extract_pdf,
    "docx": extract_docx,
    "pptx": extract_pptx,
    "xlsx": extract_xlsx,
    "html": extract_html,
}


class _DocumentNotFoundYet(Exception):
    """The dispatched document isn't visible in this transaction yet --
    almost certainly the upload-commit race described in this module's
    docstring, not a real 404 (nothing deletes a Document this early in
    its life). Caught by dispatch_extraction and retried."""


async def _run_extraction(document_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    """Returns True only when extraction actually reached
    Document.chunking_strategy being set -- the one condition
    dispatch_extraction needs before it's safe to dispatch embedding
    generation next. False (not an exception) for the honest
    "extraction_unsupported" outcome, which isn't a failure."""
    async with get_worker_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = DocumentRepository(session, tenant_id)
        document = await repo.get(document_id)
        if document is None:
            raise _DocumentNotFoundYet(str(document_id))

        extension = get_extension(document.title)
        handler = HANDLERS.get(extension)
        if handler is None:
            document.status = "extraction_unsupported"
            await session.commit()
            return False

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
            doc_metadata = build_doc_metadata(extension, content, extracted_text)
            analysis = _document_analysis_agent.analyze(extracted_text)
            doc_metadata["document_type"] = analysis.document_type
            doc_metadata["document_type_signals"] = analysis.matched_keywords
            quality = assess_quality(content, extracted_text)
            doc_metadata["quality"] = {
                "is_empty": quality.is_empty,
                "has_broken_formatting": quality.has_broken_formatting,
            }
            chunking_recommendation = _chunking_recommendation_agent.recommend(extracted_text)
            doc_metadata["chunking_recommendation"] = {
                "strategy": chunking_recommendation.strategy,
                "scores": chunking_recommendation.scores,
                "reasoning": chunking_recommendation.reasoning,
            }
        except Exception:
            document.status = "extraction_failed"
            await session.commit()
            raise

        document.status = "extracted"
        document.extracted_text = extracted_text
        document.doc_metadata = doc_metadata
        document.content_hash = quality.content_hash
        document.chunking_strategy = chunking_recommendation.strategy
        document.chunking_strategy_source = "recommended"
        document.chunking_strategy_reasoning = chunking_recommendation.reasoning
        await session.commit()
        return True


@celery_app.task(bind=True, name="dispatch_extraction", max_retries=5)  # type: ignore[untyped-decorator]
def dispatch_extraction(self: Any, document_id: str, tenant_id: str) -> None:
    try:
        extracted = asyncio.run(_run_extraction(uuid.UUID(document_id), uuid.UUID(tenant_id)))
    except _DocumentNotFoundYet as exc:
        raise self.retry(countdown=1, exc=exc) from exc
    if extracted:
        dispatch_embedding_generation.delay(document_id, tenant_id)
