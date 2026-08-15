import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agents.configuration import AgentConfiguration


class AssistantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=2000)
    agent_configuration: AgentConfiguration = Field(default_factory=AgentConfiguration)


class AssistantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    agent_configuration: AgentConfiguration
    created_at: datetime
    updated_at: datetime
