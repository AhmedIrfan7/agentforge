"""Async SQLAlchemy engine and session setup.

Every tenant-scoped table and the tenant-isolation strategy behind it are
described in docs/adr/0003-multi-tenancy-isolation-strategy.md — read that
before adding a new model here.
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from config import settings


class Base(DeclarativeBase):
    pass


# NullPool under pytest: pooled asyncpg connections get bound to whichever
# event loop first used them, but each test function gets a fresh loop —
# reusing a pooled connection across tests raises "Event loop is closed".
# Opening/closing a real connection per use avoids that entirely; production
# keeps normal pooling since it runs one process on one long-lived loop, with
# size/timeout/recycle tunable via config.py (env vars), not hardcoded here.
engine: AsyncEngine = (
    create_async_engine(settings.database_url, poolclass=NullPool)
    if settings.environment == "test"
    else create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
    )
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Set the Postgres session variable Row-Level Security policies check
    (models/mixins.py:TenantScopedMixin, migrations/rls.py). Only lasts for
    the current transaction (SET LOCAL) — call this again after each commit.

    Postgres's SET/SET LOCAL don't accept bind parameters, so the value has
    to be inlined into the SQL text. That's safe here specifically because
    tenant_id is typed as uuid.UUID, not str — there's no string to escape,
    only a fixed hex/hyphen representation. Do not change this to accept a
    raw str.
    """
    await session.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))


async def set_user_context(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Companion to set_tenant_context, for the one case a single tenant_id
    isn't enough: "which organizations does this user belong to" has to
    read Membership rows across every tenant at once, which a
    tenant_id-only RLS policy can never satisfy (there's no single
    tenant_id to set — that's literally the question being asked). See
    migrations/versions/*_add_own_membership_rls_policy.py: a second,
    separate RLS policy on memberships permits SELECT where
    user_id = this value, alongside (not instead of) the existing
    tenant_isolation policy. Same SET LOCAL / no-bind-parameters
    reasoning as set_tenant_context.
    """
    await session.execute(text(f"SET LOCAL app.current_user_id = '{user_id}'"))


async def set_lookup_token_hash(session: AsyncSession, token_hash: str) -> None:
    """Same dual-policy idea as set_user_context, applied to accepting an
    Invitation by raw token (step 074): the caller doesn't know which
    tenant the invitation belongs to yet — that's the whole question the
    token answers — so tenant_id can't be set first. A second RLS policy
    on invitations permits SELECT where token_hash matches this session
    variable (see migrations/versions/*_add_invitation_by_token_rls_policy.py).
    Once that lookup reveals the invitation's tenant_id, the caller should
    switch to set_tenant_context() for everything after.

    token_hash is always a hashlib.sha256(...).hexdigest() — exactly 64
    lowercase hex characters — so, like tenant_id being a uuid.UUID object
    above, there's nothing here that needs escaping. The check below
    makes that guarantee explicit rather than trusting the caller.
    """
    if len(token_hash) != 64 or any(c not in "0123456789abcdef" for c in token_hash):
        raise ValueError("token_hash must be a 64-character lowercase hex digest.")
    await session.execute(text(f"SET LOCAL app.lookup_token_hash = '{token_hash}'"))
