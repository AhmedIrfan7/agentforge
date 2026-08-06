"""Plain (non-tenant-scoped) DB session dependency — for routes that
operate outside any single tenant's context, e.g. creating an
Organization itself, or future platform-admin cross-tenant views
(docs/adr/0003-multi-tenancy-isolation-strategy.md). Tenant-scoped
routes use dependencies/tenant.py:get_tenant_db instead.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with get_session() as session:
        yield session
