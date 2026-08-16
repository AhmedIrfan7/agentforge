import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.configuration import AgentConfiguration


class AssistantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=20000)
    agent_configuration: AgentConfiguration = Field(default_factory=AgentConfiguration)
    # Roadmap step 192 -- opt-in anonymous/widget access. As of step
    # 238, also updatable after creation via AssistantUpdate below.
    is_public: bool = False


class AssistantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    instructions: str | None
    agent_configuration: AgentConfiguration
    is_public: bool
    created_at: datetime
    updated_at: datetime


class AssistantUpdate(BaseModel):
    # Every field optional and unset-by-default -- PATCH semantics,
    # same model_fields_set-driven pattern schemas/organization.py's
    # own OrganizationUpdate/schemas/security_settings.py's own
    # SecuritySettingsUpdate already established: only fields the
    # caller actually included get changed. name follows
    # OrganizationUpdate's own "explicit null isn't a real 'clear it'
    # value for a NOT NULL column" reasoning; description/instructions
    # are nullable, so an explicit null on either is a real, meaningful
    # "clear it" value.
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=20000)
    # A whole-object REPLACE when included, not a deep merge -- sending
    # e.g. only {"llm_provider": "anthropic"} would silently reset
    # enabled_agents/retrieval_top_k back to AgentConfiguration's own
    # class defaults, since Pydantic fills in unset nested fields from
    # ITS defaults, not from whatever the assistant's current row
    # already has. A caller changing one field must send the assistant's
    # complete current agent_configuration with that one field edited,
    # the standard, simplest correct shape for a nested-object PATCH.
    agent_configuration: AgentConfiguration | None = None
    is_public: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_cannot_be_explicitly_cleared(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("name cannot be cleared to null.")
        return value
