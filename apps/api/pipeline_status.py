"""Ingestion-pipeline per-stage status (roadmap step 111).

AGENTS.md's own "DOCUMENT PIPELINE OBSERVABILITY" section names eight
stages (upload, validation, document analysis, chunk recommendation,
chunk generation, embedding generation, vector indexing, publication).
Three of those don't have an honest per-document answer in this codebase
today, so this endpoint doesn't invent one for them rather than fake
completeness:
- upload/validation both happen synchronously before a Document row
  even exists (validation.py runs inside upload_document, before the
  insert) -- there's nothing to report that isn't already implied by
  the document existing at all.
- vector_indexing (vector_maintenance.py, step 110) is a property of
  the shared ivfflat index across ALL chunks, not any one document --
  reporting it per-document would misrepresent a table-wide index as
  document-specific state.
- publication has no real concept anywhere in this codebase yet (no
  draft/published distinction on Document) -- reporting a stage that
  doesn't exist would be worse than omitting it.

The three stages that DO have real, honestly-derivable per-document
state -- extraction (bundles upload/validation's implicit completion
plus document analysis and chunk recommendation, since extraction.py
runs all of those in one pass and one status transition, steps 090/094/
095/097), chunk_generation, and embedding_generation -- are derived from
Document.status plus real Chunk counts (repositories/chunk.py), not
guessed from Document.status alone: chunk_generation in particular is
a real database fact (chunk_count > 0), not an inference from which
status string extraction.py/embeddings_pipeline.py happens to have set,
since those two tasks can be mid-transition between each other.
"""

from dataclasses import dataclass

STAGE_NAMES = ("extraction", "chunk_generation", "embedding_generation")


@dataclass(frozen=True)
class PipelineStage:
    stage: str
    status: str  # "pending" | "in_progress" | "completed" | "failed" | "skipped" | "not_applicable"


def _extraction_stage(document_status: str) -> PipelineStage:
    if document_status == "pending":
        return PipelineStage("extraction", "pending")
    if document_status == "processing":
        return PipelineStage("extraction", "in_progress")
    if document_status == "extraction_failed":
        return PipelineStage("extraction", "failed")
    if document_status == "extraction_unsupported":
        return PipelineStage("extraction", "skipped")
    # extracted, embedding, embedded, embedding_failed all imply
    # extraction genuinely succeeded -- Document.chunking_strategy only
    # ever gets set on that success path (extraction.py).
    return PipelineStage("extraction", "completed")


def _chunk_generation_stage(document_status: str, chunk_count: int) -> PipelineStage:
    if chunk_count > 0:
        return PipelineStage("chunk_generation", "completed")
    if document_status == "embedding":
        # embeddings_pipeline.py sets status="embedding" before running
        # the chunker -- genuinely in progress, not stalled.
        return PipelineStage("chunk_generation", "in_progress")
    if document_status == "extracted":
        return PipelineStage("chunk_generation", "pending")
    if document_status == "embedding_failed":
        # Chunks are only added to the session after embedding succeeds
        # (embeddings_pipeline.py) -- a failure here means zero rows
        # ever persisted, regardless of whether the chunker itself ran
        # fine, so "not persisted" is the honest, verifiable claim.
        return PipelineStage("chunk_generation", "failed")
    return PipelineStage("chunk_generation", "not_applicable")


def _embedding_generation_stage(document_status: str) -> PipelineStage:
    if document_status == "embedded":
        return PipelineStage("embedding_generation", "completed")
    if document_status == "embedding_failed":
        return PipelineStage("embedding_generation", "failed")
    if document_status == "embedding":
        return PipelineStage("embedding_generation", "in_progress")
    return PipelineStage("embedding_generation", "not_applicable")


def compute_pipeline_stages(document_status: str, chunk_count: int) -> list[PipelineStage]:
    return [
        _extraction_stage(document_status),
        _chunk_generation_stage(document_status, chunk_count),
        _embedding_generation_stage(document_status),
    ]
