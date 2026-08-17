"""Audit-log viewer (roadmap step 247). AGENTS.md's own "AUDIT LOGGING"
sections (both copies) say audit logs should be searchable -- every
router that calls audit.py:write_audit_log() already produces real rows
(action strings like "workspace.create", "membership.role_update", one
per sensitive action across the app since step 072); this is the first
real reader. Filters cover exactly what a real investigator asks first:
which action, on what kind of resource, by whom, and in what window --
not a generic free-text search nothing here has an index for.

org_owner/admin only, same tier as security_settings:read -- audit logs
routinely contain permission changes and security events, the same
"more sensitive than day-to-day membership management" reasoning that
kept manager off security_settings:*.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from models.audit_log import AuditLog
from models.user import User
from schemas.audit_log import AuditLogListRead, AuditLogRead

router = APIRouter(prefix="/organizations/{organization_id}/audit-logs", tags=["audit-logs"])

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]

_MAX_PAGE_SIZE = 200


@router.get(
    "",
    response_model=AuditLogListRead,
    dependencies=[Depends(require_permission("audit_log:read"))],
)
async def list_audit_logs(
    session: TenantDb,
    tenant_id: TenantId,
    action: str | None = None,
    resource_type: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(le=_MAX_PAGE_SIZE, gt=0)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListRead:
    filters = [AuditLog.tenant_id == tenant_id]
    if action is not None:
        filters.append(AuditLog.action == action)
    if resource_type is not None:
        filters.append(AuditLog.resource_type == resource_type)
    if actor_user_id is not None:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if since is not None:
        filters.append(AuditLog.created_at >= since)
    if until is not None:
        filters.append(AuditLog.created_at <= until)

    total = (await session.scalar(select(func.count()).select_from(AuditLog).where(*filters))) or 0

    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()

    items = [
        AuditLogRead(
            id=log.id,
            actor_user_id=log.actor_user_id,
            actor_email=actor_email,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            extra=log.extra,
            created_at=log.created_at,
        )
        for log, actor_email in rows
    ]
    return AuditLogListRead(items=items, total=total)
