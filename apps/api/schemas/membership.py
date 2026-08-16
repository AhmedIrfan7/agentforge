import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MembershipRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role_id: uuid.UUID
    role_name: str
    role_display_name: str
    created_at: datetime


class MembershipUpdate(BaseModel):
    # A name, not an id -- same reasoning InvitationCreate.role_name
    # already established: the caller shouldn't need to know role UUIDs.
    role_name: str = Field(min_length=1, max_length=100)
