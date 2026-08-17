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

As of step 255, a no-membership denial writes a real AuditLog row
(AGENTS.md's own "AUDIT LOGGING" section names "Cross-tenant access
attempts" by name) -- tenant_id is the ORG THAT WAS TARGETED, not the
caller's own org, so its real admins see the attempt in their own
audit-log viewer (step 247), the exact "which org should see this"
question a cross-tenant probe naturally answers.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from db import get_session, set_tenant_context
from dependencies.auth import get_current_user_id
from errors import ForbiddenError
from models.user import User
from repositories.rbac import get_user_memberships
from repositories.security_settings import SecuritySettingsRepository


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
            await write_audit_log(
                session,
                tenant_id=organization_id,
                action="security.cross_tenant_attempt",
                resource_type="organization",
                resource_id=organization_id,
                actor_user_id=user_id,
            )
            await session.commit()
            raise ForbiddenError("You do not have access to this organization.")

        # security_settings.mfa_required (step 079) — the one field on
        # that model with a real enforcement point, because this is
        # already the place tenant-scoped access gets decided per
        # request. See models/security_settings.py for why
        # session_timeout/password policy don't have one yet.
        security_settings = await SecuritySettingsRepository(
            session, organization_id
        ).get_singleton()
        if security_settings is not None and security_settings.mfa_required:
            user = await session.get(User, user_id)
            if user is None or not user.mfa_enabled:
                raise ForbiddenError(
                    "This organization requires multi-factor authentication to be "
                    "enabled on your account."
                )

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
