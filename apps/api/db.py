"""Async SQLAlchemy engine and session setup.

Every tenant-scoped table and the tenant-isolation strategy behind it are
described in docs/adr/0003-multi-tenancy-isolation-strategy.md — read that
before adding a new model here.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
