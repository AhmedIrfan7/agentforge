"""Plain (non-tenant-scoped) DB session dependency — for routes that
operate outside any single tenant's context, e.g. creating an
Organization itself, or future platform-admin cross-tenant views
(docs/adr/0003-multi-tenancy-isolation-strategy.md). Tenant-scoped
routes use dependencies/tenant.py:get_tenant_db instead.

Commits automatically if the route handler completes without raising —
route code should not need to remember `await session.commit()` itself
(easy to forget, and a forgotten commit silently discards a successful
write, which is worse than a forgotten test cleanup). Rolls back on any
exception, including ones a route deliberately raises (errors.AppError
and friends). Tests use db.get_session() directly instead, specifically
to avoid this auto-commit behavior — see tests/test_tenant_isolation.py's
module docstring for why that matters there.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with get_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
