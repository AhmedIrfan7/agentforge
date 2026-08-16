import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None
    primary_color: str | None
    created_at: datetime
    updated_at: datetime


class OrganizationUpdate(BaseModel):
    # Every field optional and unset-by-default -- PATCH semantics, same
    # model_fields_set-driven pattern schemas/security_settings.py's own
    # SecuritySettingsUpdate already established: only fields the caller
    # actually included get changed, and an explicit null clears
    # logo_url/primary_color (both nullable on the model), distinct from
    # omitting them entirely.
    name: str | None = Field(default=None, min_length=1, max_length=200)
    logo_url: str | None = None
    primary_color: str | None = None

    @field_validator("name")
    @classmethod
    def _name_cannot_be_explicitly_cleared(cls, value: str | None) -> str | None:
        # Unlike logo_url/primary_color, Organization.name is NOT NULL --
        # an explicit `"name": null` isn't a meaningful "clear it" value
        # the way it is for the branding fields, it's just invalid input.
        # Only runs when the caller actually included the field (Pydantic
        # doesn't validate an omitted field's own default), so omitting
        # name entirely is still unaffected.
        if value is None:
            raise ValueError("name cannot be cleared to null.")
        return value
