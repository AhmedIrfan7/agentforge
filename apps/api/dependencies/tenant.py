"""Tenant-context resolution for FastAPI routes.

The full version of this — deriving tenant_id from an authenticated
JWT — can't be built until Milestone 2's auth work exists (roadmap
steps 060-062: there's no token to derive anything from yet). What CAN
be built now is the other half: given an already-resolved, trusted
tenant_id, wire it onto the request's DB session so Postgres RLS
(docs/adr/0003-multi-tenancy-isolation-strategy.md) actually applies.

get_current_tenant_id() below is a deliberate placeholder that raises —
NOT a stopgap that trusts a client-supplied header or query param.
AGENTS.md SECTION 9 and ADR-0003 are explicit that tenant context must
never come from client input; a "just read X-Tenant-Id for now" shortcut
here would be exactly the footgun those documents warn about, and it's
easy to forget to remove later. Once JWT auth exists, this is the one
function that changes — every route already wired against get_tenant_db
below picks up real tenant resolution automatically, no route code changes.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, set_tenant_context


async def get_current_tenant_id() -> uuid.UUID:
    raise NotImplementedError(
        "Tenant resolution from an authenticated JWT isn't built yet — "
        "see docs/ROADMAP.md Milestone 2 (steps 060-062). Override this "
        "dependency (FastAPI dependency_overrides, or replace this "
        "function's body once JWT auth exists) rather than trusting any "
        "client-supplied value for tenant_id."
    )


async def get_tenant_db(
    tenant_id: Annotated[uuid.UUID, Depends(get_current_tenant_id)],
) -> AsyncGenerator[AsyncSession]:
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        yield session
