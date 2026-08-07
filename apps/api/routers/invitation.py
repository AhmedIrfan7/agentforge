"""Invite-teammate endpoint (roadmap step 073) and invitation-accept
endpoint (074).

Accept lives on its own router, not nested under
/organizations/{organization_id} like create — the whole point of the
token is that the caller doesn't know (or need to know) which
organization it belongs to ahead of time; that's resolved from the token
itself via repositories/invitation.py:get_invitation_by_token_hash, not
a path param.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from audit import write_audit_log
from auth.verification import generate_invitation_token, hash_verification_token
from config import settings
from db import set_tenant_context
from dependencies.auth import get_current_user_id
from dependencies.db import get_db
from dependencies.rbac import require_permission
from dependencies.tenant import get_current_tenant_id, get_tenant_db
from errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from models.membership import Membership
from notifications.email import send_email
from repositories.invitation import InvitationRepository, get_invitation_by_token_hash
from repositories.role import RoleRepository
from repositories.user import UserRepository
from repositories.workspace import WorkspaceRepository
from schemas.invitation import InvitationAcceptRequest, InvitationCreate, InvitationRead

router = APIRouter(prefix="/organizations/{organization_id}/invitations", tags=["invitations"])
accept_router = APIRouter(prefix="/invitations", tags=["invitations"])

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


@accept_router.post("/accept", status_code=204)
async def accept_invitation(
    body: InvitationAcceptRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: CurrentUserId,
) -> None:
    token_hash = hash_verification_token(body.token)
    invitation = await get_invitation_by_token_hash(session, token_hash)

    invalid_invitation = UnauthorizedError("Invalid or expired invitation.")
    if invitation is None:
        raise invalid_invitation
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise invalid_invitation
    if invitation.expires_at < datetime.now(UTC):
        raise invalid_invitation

    user = await UserRepository(session).get(user_id)
    if user is None:
        raise invalid_invitation
    # A valid, unexpired token for someone else's inbox — not the same
    # failure as an invalid token, and not sensitive to spell out: the
    # caller already proved possession of a real invitation, just for a
    # different account.
    if user.email != invitation.email:
        raise ForbiddenError("This invitation was sent to a different email address.")

    await set_tenant_context(session, invitation.tenant_id)
    try:
        session.add(
            Membership(
                tenant_id=invitation.tenant_id,
                user_id=user_id,
                workspace_id=invitation.workspace_id,
                role_id=invitation.role_id,
            )
        )
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("You are already a member of this organization.") from exc

    invitation.accepted_at = datetime.now(UTC)

    await write_audit_log(
        session,
        tenant_id=invitation.tenant_id,
        action="invitation.accept",
        resource_type="invitation",
        resource_id=invitation.id,
        actor_user_id=user_id,
    )
