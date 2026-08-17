"""API-key management endpoints (roadmap step 241).

Create/list/revoke are real: a caller with api_key:create actually
gets back a working, hashed-at-rest credential; api_key:read lists
every key's own name/prefix/creator/revoked state, never the raw
secret or its hash; api_key:delete soft-revokes (revoked_at set, same
Session/Invitation pattern already established -- a key is never
deleted outright, since "this key existed and was later revoked" is
itself real audit-relevant history).

Deliberately does NOT wire API-key authentication into the rest of
this API -- see models/api_key.py's own docstring for why that's real,
separate, future work this step's literal wording doesn't ask for.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from auth.api_keys import generate_api_key
from dependencies.auth import get_current_user_id
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import NotFoundError
from repositories.api_key import ApiKeyRepository
from schemas.api_key import ApiKeyCreate, ApiKeyCreateResponse, ApiKeyRead
from schemas.common import Page, PaginationParams

router = APIRouter(prefix="/organizations/{organization_id}/api-keys", tags=["api-keys"])

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=201,
    dependencies=[Depends(require_permission("api_key:create"))],
)
async def create_api_key(
    body: ApiKeyCreate, session: TenantDb, tenant_id: TenantId, user_id: CurrentUserId
) -> ApiKeyCreateResponse:
    raw_key, key_hash, key_prefix = generate_api_key()
    repo = ApiKeyRepository(session, tenant_id)
    api_key = await repo.create(
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        created_by_user_id=user_id,
    )

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="api_key.create",
        resource_type="api_key",
        resource_id=api_key.id,
        actor_user_id=user_id,
    )

    return ApiKeyCreateResponse(
        id=api_key.id,
        tenant_id=api_key.tenant_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        created_by_user_id=api_key.created_by_user_id,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
        key=raw_key,
    )


@router.get(
    "",
    response_model=Page[ApiKeyRead],
    dependencies=[Depends(require_permission("api_key:read"))],
)
async def list_api_keys(
    session: TenantDb, tenant_id: TenantId, pagination: Annotated[PaginationParams, Depends()]
) -> Page[ApiKeyRead]:
    repo = ApiKeyRepository(session, tenant_id)
    api_keys = await repo.list(limit=pagination.limit, offset=pagination.offset)
    total = await repo.count()
    return Page(
        items=[ApiKeyRead.model_validate(k) for k in api_keys],
        limit=pagination.limit,
        offset=pagination.offset,
        total=total,
    )


@router.delete(
    "/{api_key_id}",
    status_code=204,
    dependencies=[Depends(require_permission("api_key:delete"))],
)
async def revoke_api_key(
    api_key_id: uuid.UUID, session: TenantDb, tenant_id: TenantId, user_id: CurrentUserId
) -> None:
    repo = ApiKeyRepository(session, tenant_id)
    api_key = await repo.get(api_key_id)
    if api_key is None:
        raise NotFoundError(f"API key {api_key_id} not found.")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)

        await write_audit_log(
            session,
            tenant_id=tenant_id,
            action="api_key.revoke",
            resource_type="api_key",
            resource_id=api_key.id,
            actor_user_id=user_id,
        )
