"""Per-organization security policy (roadmap step 079): session timeout
and password policy fields exist as configuration now, but neither has a
real enforcement point yet and this model doesn't pretend otherwise — see
routers/security_settings.py's module docstring for the honest reason
why (User and Session are global identities, not org-scoped, so there's
no clean place to apply an org's policy to either without redesigning
what a session means in this system). mfa_required is the exception: it
IS enforced, at dependencies/tenant.py:get_current_tenant_id, because
Membership already is tenant-scoped and MFA (step 078) is already a real
per-user mechanism — that enforcement point already exists, nothing new
to build for it.

One row per organization, auto-created alongside it in
routers/organization.py:create_organization (same pattern as the
auto-created org_owner Membership) — simpler than a nullable "no
settings yet" state to special-case everywhere this gets read.
"""

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from models.mixins import TenantScopedEntity, TimestampMixin


class SecuritySettings(TenantScopedEntity, TimestampMixin, Base):
    __tablename__ = "security_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_security_settings_tenant_id"),)

    # None = platform default (config.jwt_refresh_token_ttl_days and
    # friends) — configuration only for now, see module docstring.
    session_timeout_minutes: Mapped[int | None] = mapped_column(nullable=True)
    password_min_length: Mapped[int | None] = mapped_column(nullable=True)
    password_require_uppercase: Mapped[bool] = mapped_column(default=False, nullable=False)
    password_require_number: Mapped[bool] = mapped_column(default=False, nullable=False)
    password_require_symbol: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Enforced — see module docstring.
    mfa_required: Mapped[bool] = mapped_column(default=False, nullable=False)
