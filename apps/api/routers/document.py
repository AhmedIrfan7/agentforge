"""File upload endpoint (roadmap step 084), nested three levels under
organization
(/organizations/{id}/workspaces/{id}/knowledge-bases/{id}/documents).

Deliberately narrow scope, matching what this step actually asks for:
- File-type allow-list validation (step 085), size-limit enforcement
  (step 086, validation.py), and a virus/malware scan (step 087,
  antivirus.py) all run before anything is stored.
- Processing pipeline (steps 090+): upload_document dispatches
  extraction.py:dispatch_extraction as its very last step, after the
  Document row and audit log entry are both written. get_document_status
  (step 088) reports whatever that task sets -- "processing" while it
  runs, then "extracted"/"extraction_unsupported"/"extraction_failed"
  depending on outcome. As of step 093, every extension this endpoint
  will accept (validation.py:ALLOWED_EXTENSIONS) has a real extraction
  handler -- "extraction_unsupported" is defined but not currently
  reachable through any upload this API accepts.
- delete_document (step 116) is the delete endpoint this docstring used
  to defer -- Chunk (105) and DocumentVersion (115) both cascade at the
  DB level (ondelete="CASCADE"), so nothing here deletes those rows
  explicitly; the real remaining work is storage_key cleanup, which
  Postgres FKs can't do (storage.py:delete_file, step 116).
- override_chunking_strategy (step 103, real Document columns as of
  step 104) is document:update -- this project's first document-
  mutation permission beyond create, same tier as document:create/read
  (org_owner/admin/manager). Nothing dispatches real chunking against
  this choice yet -- step 105 creates the Chunk model first.

get_target_knowledge_base (roadmap step 120, promoted to
dependencies/knowledge_base.py once routers/retrieval.py became a
second real consumer of the identical cross-check logic) verifies the
URL's knowledge_base_id belongs to the resolved workspace_id -- same
"path param is a hint, not a trust boundary" reasoning as every other
nested resource dependency in this codebase (dependencies/tenant.py,
routers/knowledge_base.py:get_target_workspace).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from agents.chunking_recommendation import STRATEGY_NAMES
from antivirus import scan_for_viruses
from audit import write_audit_log
from config import settings
from dependencies.auth import get_current_user_id
from dependencies.knowledge_base import TargetKnowledgeBase
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from embeddings_pipeline import dispatch_embedding_generation
from errors import ConflictError, InvalidChunkingStrategyError, NotFoundError
from extraction import dispatch_extraction
from pipeline_status import compute_pipeline_stages
from repositories.chunk import ChunkRepository
from repositories.document import DocumentRepository
from repositories.document_version import DocumentVersionRepository
from schemas.common import Page, PaginationParams
from schemas.document import (
    ChunkingDecisionRead,
    ChunkingStrategyOverrideRequest,
    DocumentPipelineStatusRead,
    DocumentRead,
    DocumentStatusRead,
    DocumentVersionRead,
    PipelineStageRead,
)
from storage import delete_file, ensure_bucket_exists, upload_file
from validation import read_upload_content, validate_upload

router = APIRouter(
    prefix=(
        "/organizations/{organization_id}/workspaces/{workspace_id}"
        "/knowledge-bases/{knowledge_base_id}/documents"
    ),
    tags=["documents"],
)

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]
UserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


@router.post(
    "",
    response_model=DocumentRead,
    status_code=201,
    dependencies=[Depends(require_permission("document:create"))],
)
async def upload_document(
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    knowledge_base: TargetKnowledgeBase,
    file: Annotated[UploadFile, File()],
) -> DocumentRead:
    content = await read_upload_content(file, settings.max_upload_size_bytes)
    validate_upload(file.filename, content)
    await scan_for_viruses(content)

    document_id = uuid.uuid4()
    storage_key = f"{tenant_id}/{knowledge_base.id}/{document_id}/{file.filename}"

    await ensure_bucket_exists()
    await upload_file(
        key=storage_key,
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )

    repo = DocumentRepository(session, tenant_id)
    document = await repo.create(
        id=document_id,
        knowledge_base_id=knowledge_base.id,
        title=file.filename or "Untitled",
        storage_key=storage_key,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
    )

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="document.create",
        resource_type="document",
        resource_id=document.id,
        actor_user_id=user_id,
    )

    dispatch_extraction.delay(str(document.id), str(tenant_id))

    return DocumentRead.model_validate(document)


@router.get(
    "",
    response_model=Page[DocumentRead],
    dependencies=[Depends(require_permission("document:read"))],
)
async def list_documents(
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
    pagination: Annotated[PaginationParams, Depends()],
) -> Page[DocumentRead]:
    repo = DocumentRepository(session, tenant_id)
    documents = await repo.list_for_knowledge_base(
        knowledge_base.id, limit=pagination.limit, offset=pagination.offset
    )
    total = await repo.count_for_knowledge_base(knowledge_base.id)
    return Page(
        items=[DocumentRead.model_validate(d) for d in documents],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    dependencies=[Depends(require_permission("document:read"))],
)
async def get_document(
    document_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> DocumentRead:
    repo = DocumentRepository(session, tenant_id)
    document = await repo.get(document_id)
    if document is None or document.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Document {document_id} not found.")
    return DocumentRead.model_validate(document)


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusRead,
    dependencies=[Depends(require_permission("document:read"))],
)
async def get_document_status(
    document_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> DocumentStatusRead:
    """Roadmap step 088 -- a cheap endpoint for a client to poll after
    upload, separate from get_document above so repeated polling doesn't
    re-fetch title/doc_metadata/content_type/etc. on every tick. No new
    permission: reading a document's status is the same capability as
    reading the document itself, just a smaller view of it."""
    repo = DocumentRepository(session, tenant_id)
    document = await repo.get(document_id)
    if document is None or document.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Document {document_id} not found.")
    return DocumentStatusRead.model_validate(document)


@router.get(
    "/{document_id}/pipeline-status",
    response_model=DocumentPipelineStatusRead,
    dependencies=[Depends(require_permission("document:read"))],
)
async def get_document_pipeline_status(
    document_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
) -> DocumentPipelineStatusRead:
    """Roadmap step 111 -- per-stage breakdown (pipeline_status.py),
    distinct from get_document_status above: that endpoint is a cheap
    single-string poll target, this one is for a client that wants to
    show real ingestion progress. Same document:read permission -- a
    richer view of the same capability, not a new one."""
    repo = DocumentRepository(session, tenant_id)
    document = await repo.get(document_id)
    if document is None or document.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Document {document_id} not found.")

    chunk_repo = ChunkRepository(session, tenant_id)
    chunk_count = await chunk_repo.count_for_document(document_id)
    embedded_chunk_count = await chunk_repo.count_embedded_for_document(document_id)
    stages = compute_pipeline_stages(document.status, chunk_count)

    return DocumentPipelineStatusRead(
        id=document.id,
        status=document.status,
        stages=[PipelineStageRead(stage=s.stage, status=s.status) for s in stages],
        chunk_count=chunk_count,
        embedded_chunk_count=embedded_chunk_count,
        updated_at=document.updated_at,
    )


@router.patch(
    "/{document_id}/chunking-strategy",
    response_model=ChunkingDecisionRead,
    dependencies=[Depends(require_permission("document:update"))],
)
async def override_chunking_strategy(
    document_id: uuid.UUID,
    body: ChunkingStrategyOverrideRequest,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    knowledge_base: TargetKnowledgeBase,
) -> ChunkingDecisionRead:
    """Roadmap step 103 (endpoint), step 104 (real columns instead of
    doc_metadata) -- one endpoint covers both "accept" and "override":
    the caller always states the strategy they want, and whichever one
    they send is compared against doc_metadata["chunking_recommendation"]
    (extraction.py's own recommendation, if one exists yet -- the
    ORIGINAL recommendation, which never changes, not the current
    chunking_strategy column value, which does as overrides happen; that
    distinction is what keeps a second override still correctly naming
    what was actually recommended) to decide source ("accepted" vs
    "override")."""
    if body.strategy not in STRATEGY_NAMES:
        raise InvalidChunkingStrategyError(
            f"'{body.strategy}' is not a recognized chunking strategy. "
            f"Allowed strategies: {', '.join(STRATEGY_NAMES)}."
        )

    repo = DocumentRepository(session, tenant_id)
    document = await repo.get(document_id)
    if document is None or document.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Document {document_id} not found.")

    existing_recommendation = document.doc_metadata.get("chunking_recommendation")
    recommended_strategy: object = None
    recommended_reasoning = ""
    if isinstance(existing_recommendation, dict):
        recommended_strategy = existing_recommendation.get("strategy")
        recommended_reasoning = str(existing_recommendation.get("reasoning", ""))

    if body.strategy == recommended_strategy:
        source = "accepted"
        reasoning = recommended_reasoning
    else:
        source = "override"
        reasoning = (
            f"Manually set to '{body.strategy}', overriding the recommended "
            f"'{recommended_strategy}'."
            if recommended_strategy is not None
            else f"Manually set to '{body.strategy}' (no recommendation existed yet)."
        )

    document.chunking_strategy = body.strategy
    document.chunking_strategy_source = source
    document.chunking_strategy_reasoning = reasoning
    await session.flush()

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="document.chunking_strategy_override",
        resource_type="document",
        resource_id=document.id,
        actor_user_id=user_id,
    )

    return ChunkingDecisionRead(strategy=body.strategy, source=source, reasoning=reasoning)


@router.post(
    "/{document_id}/reindex",
    response_model=DocumentStatusRead,
    status_code=202,
    dependencies=[Depends(require_permission("document:update"))],
)
async def reindex_document(
    document_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    knowledge_base: TargetKnowledgeBase,
) -> DocumentStatusRead:
    """Roadmap step 114 -- re-runs chunk generation + embedding
    generation (embeddings_pipeline.py:dispatch_embedding_generation,
    unchanged, reused as-is) against the document's CURRENT
    chunking_strategy. Closes a real, previously documented tension:
    overriding chunking_strategy (step 103) never used to actually
    regenerate a document's chunks -- this is that missing trigger,
    explicit rather than automatic, so a caller reviews/overrides first
    (103) and then deliberately re-indexes (this endpoint), not a
    silent re-chunk on every override.

    409, not 404 or 422 -- the document exists and the request is
    well-formed, but re-indexing something that was never successfully
    extracted (no chunking_strategy set yet) isn't a valid action on
    this resource right now, the same "right resource, wrong state"
    reasoning Invitation's already-accepted 409 uses elsewhere in this
    codebase. document:update, same permission the override endpoint
    already requires -- this is a further mutation of the same
    document-processing-decision capability, not a new one.

    Async, same shape as upload_document dispatching extraction: 202
    Accepted with the current (still "embedded"/"embedding_failed" from
    the PREVIOUS run) status, not the finished result -- a client polls
    .../status or .../pipeline-status afterward, same as it already does
    after upload."""
    repo = DocumentRepository(session, tenant_id)
    document = await repo.get(document_id)
    if document is None or document.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Document {document_id} not found.")
    if document.chunking_strategy is None:
        raise ConflictError(
            f"Document {document_id} has no chunking strategy set yet -- "
            "it must be successfully extracted before it can be re-indexed."
        )

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="document.reindex",
        resource_type="document",
        resource_id=document.id,
        actor_user_id=user_id,
    )

    dispatch_embedding_generation.delay(str(document.id), str(tenant_id))
    return DocumentStatusRead.model_validate(document)


@router.post(
    "/{document_id}/versions",
    response_model=DocumentRead,
    status_code=201,
    dependencies=[Depends(require_permission("document:update"))],
)
async def replace_document_content(
    document_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    knowledge_base: TargetKnowledgeBase,
    file: Annotated[UploadFile, File()],
) -> DocumentRead:
    """Roadmap step 115 -- uploading here REPLACES the document's
    current content; its previous state is snapshotted into a new
    DocumentVersion row first, not discarded ("replace preserves
    history"). Same validation/antivirus pipeline as the original
    upload (upload_document above) -- a replacement file is exactly as
    untrusted as a first-time one.

    The snapshot copies Document's own fields (title/storage_key/
    content_type/size_bytes/doc_metadata/extracted_text/content_hash/
    chunking decision) -- not Chunk rows. Chunks belong to whatever
    content is CURRENT (step 114 already established a document has
    exactly one live chunk set at a time); the new upload's extraction
    will naturally replace them once it completes, the same
    dispatch_extraction -> dispatch_embedding_generation chain every
    upload goes through.

    The new file gets a fresh, randomized storage_key rather than
    reusing upload_document's own {tenant}/{kb}/{document_id}/{filename}
    convention -- reusing that pattern here (same document_id, likely
    same filename) would overwrite the OLD object in MinIO/S3, defeating
    "preserves history" at the storage layer before a version row could
    even point at it."""
    repo = DocumentRepository(session, tenant_id)
    document = await repo.get(document_id)
    if document is None or document.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Document {document_id} not found.")

    content = await read_upload_content(file, settings.max_upload_size_bytes)
    validate_upload(file.filename, content)
    await scan_for_viruses(content)

    version_repo = DocumentVersionRepository(session, tenant_id)
    next_version_number = await version_repo.count_for_document(document_id) + 1
    await version_repo.create(
        document_id=document.id,
        version_number=next_version_number,
        title=document.title,
        storage_key=document.storage_key,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        doc_metadata=document.doc_metadata,
        extracted_text=document.extracted_text,
        content_hash=document.content_hash,
        chunking_strategy=document.chunking_strategy,
        chunking_strategy_source=document.chunking_strategy_source,
        chunking_strategy_reasoning=document.chunking_strategy_reasoning,
    )

    new_storage_key = (
        f"{tenant_id}/{knowledge_base.id}/{document_id}/{uuid.uuid4()}/{file.filename}"
    )
    await ensure_bucket_exists()
    await upload_file(
        key=new_storage_key,
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )

    document.title = file.filename or document.title
    document.storage_key = new_storage_key
    document.content_type = file.content_type or "application/octet-stream"
    document.size_bytes = len(content)
    document.status = "pending"
    document.doc_metadata = {}
    document.extracted_text = None
    document.content_hash = None
    document.chunking_strategy = None
    document.chunking_strategy_source = None
    document.chunking_strategy_reasoning = None
    await session.flush()
    # updated_at is server-computed (onupdate=func.now(), models/mixins.py)
    # -- unlike upload_document's freshly-INSERTed Document, whose defaults
    # populate automatically, an UPDATEd row's onupdate value isn't known
    # in-memory after flush() alone. Without this, DocumentRead.model_
    # validate(document) below tries to lazily reload it outside the
    # active async context and raises MissingGreenlet (caught live while
    # writing this endpoint, not assumed).
    await session.refresh(document)

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="document.replace",
        resource_type="document",
        resource_id=document.id,
        actor_user_id=user_id,
    )

    dispatch_extraction.delay(str(document.id), str(tenant_id))

    return DocumentRead.model_validate(document)


@router.get(
    "/{document_id}/versions",
    response_model=Page[DocumentVersionRead],
    dependencies=[Depends(require_permission("document:read"))],
)
async def list_document_versions(
    document_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    knowledge_base: TargetKnowledgeBase,
    pagination: Annotated[PaginationParams, Depends()],
) -> Page[DocumentVersionRead]:
    repo = DocumentRepository(session, tenant_id)
    document = await repo.get(document_id)
    if document is None or document.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Document {document_id} not found.")

    version_repo = DocumentVersionRepository(session, tenant_id)
    versions = await version_repo.list_for_document(
        document_id, limit=pagination.limit, offset=pagination.offset
    )
    total = await version_repo.count_for_document(document_id)
    return Page(
        items=[DocumentVersionRead.model_validate(v) for v in versions],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.delete(
    "/{document_id}",
    status_code=204,
    dependencies=[Depends(require_permission("document:delete"))],
)
async def delete_document(
    document_id: uuid.UUID,
    session: TenantDb,
    tenant_id: TenantId,
    user_id: UserId,
    knowledge_base: TargetKnowledgeBase,
) -> None:
    """Roadmap step 116 -- deletes a document and everything that
    belongs to it. Chunk (105) and DocumentVersion (115) rows cascade
    automatically at the DB level (ondelete="CASCADE" foreign keys) --
    nothing here deletes them explicitly. Storage objects are NOT
    covered by any FK, so they're deleted explicitly: the document's
    own current storage_key plus every DocumentVersion's own historical
    storage_key (step 115's own live verification surfaced that neither
    org deletion nor anything else in this codebase cleans up MinIO
    objects -- this is the one place that actually does, for a
    document's own storage footprint).

    Storage cleanup runs BEFORE the DB delete, not after: if a storage
    delete fails partway, the Document/DocumentVersion rows (and their
    audit trail) stay intact for a retry or investigation, rather than
    the DB row disappearing first and leaving orphaned, now-undiscoverable
    objects in MinIO with nothing left pointing at them.

    document:delete, not document:update -- deleting is a genuinely
    more destructive, harder-to-undo action than updating processing
    config or replacing content, worth its own explicit grant even
    though it lands at the same org_owner/admin/manager tier (same
    precedent knowledge_base:delete already set at 082: siblings under
    one parent resource don't need a stricter delete tier than their
    own create/read/update, just a distinct permission key)."""
    repo = DocumentRepository(session, tenant_id)
    document = await repo.get(document_id)
    if document is None or document.knowledge_base_id != knowledge_base.id:
        raise NotFoundError(f"Document {document_id} not found.")

    version_repo = DocumentVersionRepository(session, tenant_id)
    versions = await version_repo.list_all_for_document(document_id)
    for version in versions:
        await delete_file(version.storage_key)
    await delete_file(document.storage_key)

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="document.delete",
        resource_type="document",
        resource_id=document.id,
        actor_user_id=user_id,
    )

    await repo.delete(document)
