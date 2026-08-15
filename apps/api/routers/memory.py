"""Memory-privacy controls (roadmap step 169, AGENTS.md's own
"PERSONALIZED EXPERIENCE" section: "Privacy controls must always be
respected"). View/export/delete the CURRENT user's own `scope="user"`
memory -- deliberately never organization- or session-scoped memory,
neither of which is "theirs" to control this way; deleting one's own
memory here is a granular, individual-entry operation, not the
comprehensive account-wide "right to erasure" step 170 owns
separately.

No `require_permission(...)` gate, unlike every org-admin router in
this codebase -- the same self-service shape `routers/mfa.py` already
established for "manage my own account" endpoints: real authentication
(`get_current_user_id`) plus real tenant membership (`get_tenant_db`,
which already 403s a non-member) is the correct and sufficient bar for
a user managing their own data. Requiring a separately-granted
permission to see or delete one's OWN memory would be backwards --
nobody else's permission grant should gate that.

Nested under `/organizations/{organization_id}/memory` rather than a
bare `/me/memory` -- `Memory` is tenant-scoped
(`models/memory.py:Memory`, 162) and a user can belong to more than
one organization (`Membership`), so which org's memory is in view is a
real, necessary part of the request, the same reason every other
resource in this codebase nests under an explicit `organization_id`.

`DELETE /{memory_id}` checks `memory.user_id == user_id` before
deleting, not just that the memory exists in this tenant -- a
user-scoped memory belonging to a DIFFERENT user in the same
organization must 404, not silently succeed just because the caller
has membership in the org (same "ownership check, not just existence
check" discipline every other resource-scoping check in this codebase
already applies).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_user_id
from dependencies.tenant import get_tenant_db
from errors import NotFoundError
from repositories.memory import MemoryRepository
from schemas.common import Page, PaginationParams
from schemas.memory import MemoryRead

router = APIRouter(prefix="/organizations/{organization_id}/memory", tags=["memory"])

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


@router.get("", response_model=Page[MemoryRead])
async def list_my_memory(
    organization_id: uuid.UUID,
    session: TenantDb,
    user_id: CurrentUserId,
    pagination: Annotated[PaginationParams, Depends()],
) -> Page[MemoryRead]:
    repo = MemoryRepository(session, organization_id)
    memories = await repo.list_for_user(user_id, limit=pagination.limit, offset=pagination.offset)
    total = await repo.count_for_user(user_id)
    return Page(
        items=[MemoryRead.model_validate(m) for m in memories],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.get("/export", response_model=list[MemoryRead])
async def export_my_memory(
    organization_id: uuid.UUID, session: TenantDb, user_id: CurrentUserId
) -> list[MemoryRead]:
    repo = MemoryRepository(session, organization_id)
    memories = await repo.list_all_for_user(user_id)
    return [MemoryRead.model_validate(m) for m in memories]


@router.delete("/{memory_id}", status_code=204)
async def delete_my_memory(
    organization_id: uuid.UUID, memory_id: uuid.UUID, session: TenantDb, user_id: CurrentUserId
) -> None:
    repo = MemoryRepository(session, organization_id)
    memory = await repo.get(memory_id)
    if memory is None or memory.user_id != user_id:
        raise NotFoundError(f"Memory {memory_id} not found.")
    await repo.delete(memory)
