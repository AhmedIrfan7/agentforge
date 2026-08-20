import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    created_at: datetime
    is_platform_admin: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MfaRequiredResponse(BaseModel):
    """Returned instead of TokenResponse by login/magic-link-verify/
    oauth-callback when the user has MFA enabled — mfa_required lets a
    client distinguish this from a real TokenResponse without relying on
    status code alone (both are 200; a wrong-password 401 stays 401)."""

    mfa_required: bool = True
    mfa_ticket: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkVerifyRequest(BaseModel):
    token: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=200)


class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaConfirmResponse(BaseModel):
    # Shown exactly once — only the hashes are ever stored
    # (models/mfa_backup_code.py). The client is responsible for
    # displaying these somewhere the user can save them; this API has no
    # way to show them again.
    backup_codes: list[str]


class MfaVerifyRequest(BaseModel):
    mfa_ticket: str = Field(min_length=1)
    # A TOTP code (6 digits) or a backup code (10 lowercase letters/
    # digits, models/mfa_backup_code.py) — routers/mfa.py tries both, so
    # this deliberately isn't length-constrained to just one shape.
    code: str = Field(min_length=1, max_length=200)


class MfaDisableRequest(BaseModel):
    # Proof the caller still controls at least one factor before turning
    # MFA off — either their current password or a valid TOTP/backup
    # code, whichever they still have.
    password: str | None = None
    code: str | None = None
