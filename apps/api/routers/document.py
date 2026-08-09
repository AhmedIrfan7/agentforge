"""File upload endpoint (roadmap step 084), nested three levels under
organization
(/organizations/{id}/workspaces/{id}/knowledge-bases/{id}/documents).

Deliberately narrow scope, matching what this step actually asks for:
- File-type allow-list validation (step 085), size-limit enforcement
  (step 086, validation.py), and a virus/malware scan (step 087,
  antivirus.py) all run before anything is stored.
- No processing pipeline (steps 090+) -- status starts and stays
  "pending" after upload; nothing dispatches extraction yet, so
  get_document_status (step 088) has nothing but "pending" to ever
  report until that lands. It's still real, useful surface area now:
  the polling contract a client can already integrate against, and
  every future pipeline stage just needs to set document.status to a
  new value for it to show up here, no route changes required.
- No delete endpoint -- step 116 ("tenant-scoped document deletion")
  owns that, and it needs to cascade chunks/embeddings that don't exist
  yet either. A bare delete now would just be replaced.

get_target_knowledge_base cross-checks the URL's knowledge_base_id (and
transitively, via get_target_workspace-equivalent logic inlined here,
workspace_id) against real rows in the resolved tenant -- same "path
param is a hint, not a trust boundary" reasoning as every other nested
resource dependency in this codebase (dependencies/tenant.py,
routers/knowledge_base.py:get_target_workspace).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from antivirus import scan_for_viruses
from audit import write_audit_log
from config import settings
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import NotFoundError
from models.knowledge_base import KnowledgeBase
from repositories.document import DocumentRepository
from repositories.knowledge_base import KnowledgeBaseRepository
from schemas.common import Page, PaginationParams
from schemas.document import DocumentRead, DocumentStatusRead
from storage import ensure_bucket_exists, upload_file
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


async def get_target_knowledge_base(
    knowledge_base_id: uuid.UUID, workspace_id: uuid.UUID, session: TenantDb, tenant_id: TenantId
) -> KnowledgeBase:
    knowledge_base = await KnowledgeBaseRepository(session, tenant_id).get(knowledge_base_id)
    if knowledge_base is None or knowledge_base.workspace_id != workspace_id:
        raise NotFoundError(f"Knowledge base {knowledge_base_id} not found.")
    return knowledge_base


TargetKnowledgeBase = Annotated[KnowledgeBase, Depends(get_target_knowledge_base)]


@router.post(
    "",
    response_model=DocumentRead,
    status_code=201,
    dependencies=[Depends(require_permission("document:create"))],
)
async def upload_document(
    session: TenantDb,
    tenant_id: TenantId,
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
    )
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
