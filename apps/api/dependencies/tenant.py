"""Tenant-context resolution for FastAPI routes.

get_current_tenant_id() used to be a deliberate NotImplementedError
placeholder (see git history / AGENTS.md SECTION 9 / ADR-0003 for why it
was never a "just read X-Tenant-Id" shortcut) until JWT auth existed to
resolve a real, trusted identity from. It now does the real thing:
organization_id comes from the URL path (every route using get_tenant_db
must declare {organization_id}), and get_current_user_id resolves who's
asking from their JWT — but the organization_id is only ever TRUSTED
once it's cross-checked against that user's actual Membership rows, not
because the client claimed it. A user with no membership in that org
gets 403, same as if the org query returned nothing.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, set_tenant_context
from dependencies.auth import get_current_user_id
from errors import ForbiddenError
from repositories.rbac import get_user_memberships


async def get_current_tenant_id(
    organization_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
) -> uuid.UUID:
    async with get_session() as session:
        # Membership is RLS-protected (tenant_isolation policy) — without
        # this, the query below silently returns zero rows for everyone,
        # including the actual owner, and every route 403s unconditionally.
        await set_tenant_context(session, organization_id)
        memberships = await get_user_memberships(
            session, user_id=user_id, tenant_id=organization_id
        )
    if not memberships:
        raise ForbiddenError("You do not have access to this organization.")
    return organization_id


async def get_tenant_db(
    tenant_id: Annotated[uuid.UUID, Depends(get_current_tenant_id)],
) -> AsyncGenerator[AsyncSession]:
    # Commits automatically on a clean exit, rolls back on any exception —
    # see dependencies/db.py:get_db's docstring for why. SET LOCAL from
    # set_tenant_context lasts exactly as long as this one transaction,
    # which is exactly the request's lifetime here.
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
