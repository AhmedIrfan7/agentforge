import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrganizationSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    workspace_count: int
    member_count: int
    conversation_count: int
    document_count: int


class PlatformOrganizationsRead(BaseModel):
    organizations: list[OrganizationSummaryRead]
