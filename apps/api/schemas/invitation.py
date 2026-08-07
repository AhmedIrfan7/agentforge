import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=1)


class InvitationCreate(BaseModel):
    email: EmailStr
    # A name, not an id: the caller shouldn't need to know role UUIDs to
    # invite someone, same reasoning as create_organization not requiring
    # a role_id for the auto-created org_owner membership.
    role_name: str = Field(min_length=1, max_length=100)
    workspace_id: uuid.UUID | None = None


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role_id: uuid.UUID
    workspace_id: uuid.UUID | None
    invited_by_user_id: uuid.UUID
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
