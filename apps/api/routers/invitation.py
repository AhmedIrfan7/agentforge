"""Invite-teammate endpoint (roadmap step 073). Accepting an invitation
(074) is deliberately not here yet — that flow needs to look up an
Invitation by raw token alone, before any tenant context exists, which
needs its own RLS policy (same problem Membership solved with the
own_memberships policy in migration 03c691d922d4) — a decision for when
074 actually adds that endpoint, not before.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from auth.verification import generate_invitation_token
from config import settings
from dependencies.auth import get_current_user_id
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import ConflictError, NotFoundError
from notifications.email import send_email
from repositories.invitation import InvitationRepository
from repositories.role import RoleRepository
from repositories.workspace import WorkspaceRepository
from schemas.invitation import InvitationCreate, InvitationRead

router = APIRouter(prefix="/organizations/{organization_id}/invitations", tags=["invitations"])

TenantDb = Annotated[AsyncSession, Depends(get_tenant_db)]
TenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


@router.post(
    "",
    response_model=InvitationRead,
    status_code=201,
    dependencies=[Depends(require_permission("invitation:create"))],
)
async def create_invitation(
    body: InvitationCreate, session: TenantDb, tenant_id: TenantId, user_id: CurrentUserId
) -> InvitationRead:
    role = await RoleRepository(session).get_by_name(body.role_name)
    if role is None:
        raise NotFoundError(f"Role '{body.role_name}' does not exist.")

    if body.workspace_id is not None:
        workspace = await WorkspaceRepository(session, tenant_id).get(body.workspace_id)
        if workspace is None:
            raise NotFoundError(f"Workspace {body.workspace_id} not found in this organization.")

    raw_token, token_hash, expires_at = generate_invitation_token()

    repo = InvitationRepository(session, tenant_id)
    try:
        invitation = await repo.create(
            email=body.email,
            role_id=role.id,
            workspace_id=body.workspace_id,
            invited_by_user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    except IntegrityError as exc:
        raise ConflictError(
            f"'{body.email}' already has a pending invitation to this organization."
        ) from exc

    await write_audit_log(
        session,
        tenant_id=tenant_id,
        action="invitation.create",
        resource_type="invitation",
        resource_id=invitation.id,
        actor_user_id=user_id,
    )

    link = f"{settings.app_base_url}/invitations/accept?token={raw_token}"
    send_email(
        to=body.email,
        subject="You've been invited to join an organization on AgentForge",
        body=f"Click to accept the invitation: {link}\n\nThis link expires in 7 days.",
    )

    return InvitationRead.model_validate(invitation)
