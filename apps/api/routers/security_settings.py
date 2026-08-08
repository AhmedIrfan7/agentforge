"""Per-organization security settings (roadmap step 079).

Honest about scope: session_timeout_minutes and the password_* fields
are stored and returned, but nothing in this codebase reads them yet.
User and Session (models/session.py) are global identities, not
org-scoped — the SAME login session lets a user act across every
organization they belong to, so there's no single tenant whose
session-timeout policy would even apply to it, and no clean place to
apply a per-org password policy to a global signup/password-reset flow
either, without redesigning what a session or an account means in this
system. That's real, deliberate future work, not an oversight — flagging
it here rather than pretending these fields already do something.

mfa_required is the one field that IS enforced, and needed no new
plumbing to get there: dependencies/tenant.py:get_current_tenant_id
already resolves real Membership per request, so checking the org's
mfa_required flag against the caller's User.mfa_enabled at that exact
point was the natural, minimal place to add it.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import NotFoundError
from repositories.security_settings import SecuritySettingsRepository
from schemas.security_settings import SecuritySettingsRead, SecuritySettingsUpdate

router = APIRouter(
    prefix="/organizations/{organization_id}/security-settings", tags=["security-settings"]
)

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]


@router.get(
    "",
    response_model=SecuritySettingsRead,
    dependencies=[Depends(require_permission("security_settings:read"))],
)
async def get_security_settings(session: TenantDb, tenant_id: TenantId) -> SecuritySettingsRead:
    settings_row = await SecuritySettingsRepository(session, tenant_id).get_singleton()
    if settings_row is None:
        # Shouldn't happen for any organization created after this
        # step's migration (auto-created alongside it, same as the
        # migration's backfill for organizations that predate it) — a
        # missing row means something upstream broke, not a normal 404.
        raise NotFoundError("Security settings have not been initialized for this organization.")
    return SecuritySettingsRead.model_validate(settings_row)


@router.patch(
    "",
    response_model=SecuritySettingsRead,
    dependencies=[Depends(require_permission("security_settings:update"))],
)
async def update_security_settings(
    body: SecuritySettingsUpdate, session: TenantDb, tenant_id: TenantId
) -> SecuritySettingsRead:
    settings_row = await SecuritySettingsRepository(session, tenant_id).get_singleton()
    if settings_row is None:
        raise NotFoundError("Security settings have not been initialized for this organization.")

    # Only fields the caller actually included in the request body get
    # applied — model_fields_set (not "is the value None") is what
    # distinguishes "omitted" from "explicitly cleared to null".
    for field_name in body.model_fields_set:
        setattr(settings_row, field_name, getattr(body, field_name))

    return SecuritySettingsRead.model_validate(settings_row)
