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
