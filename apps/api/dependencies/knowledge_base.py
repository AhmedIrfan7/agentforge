"""Shared knowledge-base resolution dependency (roadmap step 120,
promoted out of routers/document.py -- same "build inline for the
first consumer, promote once a second real consumer needs it" pattern
this pipeline has used throughout, e.g. Chunk (chunking_types.py),
pack_units (chunking_packing.py), rows_to_markdown (extraction_tables
.py). routers/retrieval.py is the second real consumer; routers/
document.py's own copy is replaced by this one, not duplicated a third
time.

Cross-checks the URL's knowledge_base_id against a real KnowledgeBase
row belonging to the resolved workspace_id -- same "path param is a
hint, not a trust boundary" reasoning as every other nested-resource
dependency in this codebase (dependencies/tenant.py, routers/
knowledge_base.py:get_target_workspace).
"""

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import NotFoundError
from models.knowledge_base import KnowledgeBase
from repositories.knowledge_base import KnowledgeBaseRepository

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
