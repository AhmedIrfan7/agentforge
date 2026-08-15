import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SecuritySettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    session_timeout_minutes: int | None
    password_min_length: int | None
    password_require_uppercase: bool
    password_require_number: bool
    password_require_symbol: bool
    mfa_required: bool
    allowed_domains: list[str]
    created_at: datetime
    updated_at: datetime


class SecuritySettingsUpdate(BaseModel):
    # Every field optional and unset-by-default (not defaulted to None) —
    # PATCH semantics: only fields the caller actually included get
    # changed. model_fields_set (routers/security_settings.py) is what
    # distinguishes "omitted" from "explicitly set to null."
    session_timeout_minutes: int | None = Field(default=None, ge=1)
    password_min_length: int | None = Field(default=None, ge=1, le=200)
    password_require_uppercase: bool | None = None
    password_require_number: bool | None = None
    password_require_symbol: bool | None = None
    mfa_required: bool | None = None
    # None (the field simply omitted) means "don't touch it" -- an
    # explicit [] IS a real, meaningful value (clears the restriction,
    # re-opening the assistant to every origin), distinct from omitting
    # the field entirely, same model_fields_set-driven PATCH semantics
    # every other field here already uses.
    allowed_domains: list[str] | None = None
