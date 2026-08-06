"""Audit log writer — see models/audit_log.py. Call this from routers,
not repositories: what counts as an auditable action (and what context
to attach) is a business-logic decision, not a data-access one.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_log import AuditLog


async def write_audit_log(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            extra=extra,
        )
    )
    await session.flush()
