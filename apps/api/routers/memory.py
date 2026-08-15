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

As of step 170, `DELETE` (no `{memory_id}`) adds the real, distinct
"right to erasure" operation AGENTS.md's own "AUDIT LOGGING" section
names specifically ("Memory deletion") -- comprehensive, not granular:
every one of the caller's own `scope="user"` memories in this
organization, erased in one real, audited operation, not one entry at
a time. Unlike step 169's per-entry delete, this one calls
`write_audit_log` -- a bulk erasure is exactly the kind of
consequential, compliance-relevant event `routers/document.py`/
`routers/knowledge_base.py`/`routers/assistant.py` already audit-log
their own delete operations for; `resource_type="user_memory"`/
`resource_id=user_id` represents the erasure acting on the user's
memory collection as a whole, since there is no single row it targets.
`extra={"deleted_count": ...}` records how much was actually erased,
the one detail an audit trail entry with no enumerable resource_id
still needs to be useful.

**Real, honest gap, not silently worked around:** this does NOT reach
into Redis short-term memory (`short_term_memory.py`, 163) --
short-term entries are keyed by `session_id`, and no
`user_id -> session_id` mapping exists anywhere in this codebase (no
Conversation/ConversationSession model until Milestone 6), so there is
no real way to find "every session belonging to this user" to erase
from Redis today. Short-term memory already expires on its own TTL
(one hour of inactivity); a real cross-store erasure needs a real
session index this codebase doesn't have yet.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
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


@router.delete("", status_code=204)
async def erase_my_memory(
    organization_id: uuid.UUID, session: TenantDb, user_id: CurrentUserId
) -> None:
    repo = MemoryRepository(session, organization_id)
    deleted_count = await repo.delete_all_for_user(user_id)

    await write_audit_log(
        session,
        tenant_id=organization_id,
        action="memory.erase",
        resource_type="user_memory",
        resource_id=user_id,
        actor_user_id=user_id,
        extra={"deleted_count": deleted_count},
    )


@router.delete("/{memory_id}", status_code=204)
async def delete_my_memory(
    organization_id: uuid.UUID, memory_id: uuid.UUID, session: TenantDb, user_id: CurrentUserId
) -> None:
    repo = MemoryRepository(session, organization_id)
    memory = await repo.get(memory_id)
    if memory is None or memory.user_id != user_id:
        raise NotFoundError(f"Memory {memory_id} not found.")
    await repo.delete(memory)
