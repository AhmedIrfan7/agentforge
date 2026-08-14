"""Proves routers/retrieval.py's /context endpoint caching (roadmap
step 134) actually reads/writes real Redis -- the FastAPI-wired
version is a no-op under pytest (routers/retrieval.py's own docstring
explains why, same reasoning rate_limit.py's own test file already
established), so every test here patches settings.environment to
"production" to exercise the real path.

Calls build_search_context() directly, not through TestClient/HTTP --
a real bug found while writing this: Starlette's TestClient runs the
ASGI app inside its OWN internal event loop (a separate thread/portal),
different from the outer `async def test_...()` function's own
pytest-anyio loop -- redis_client's connection ends up bound to
whichever loop touches it first, and mixing the two raised a real
"Event loop is closed" error the moment a second request tried to
reuse the connection from the wrong loop. test_rate_limit.py's own
docstring already explains why IT calls its dependency directly
instead of going through an endpoint -- the same reason applies here,
just not spelled out as explicitly there. Keeping everything (seeding,
the call, and cache invalidation checks) inside one continuous async
test function/event loop sidesteps the whole class of problem.

Kept in its own file, not test_retrieval_endpoints.py: every test here
touches redis_client for real, and closing it after each test (the
established fixture) would be wrong to force onto the ~20 unrelated,
non-caching, TestClient-based tests already in that file.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from sqlalchemy import select

from config import settings
from db import get_session, set_tenant_context
from models.chunk import Chunk
from models.document import Document
from models.knowledge_base import KnowledgeBase
from models.organization import Organization
from models.workspace import Workspace
from redis_client import redis_client
from routers.retrieval import build_search_context
from schemas.retrieval import ContextSearchRequest


@pytest.fixture(autouse=True)
async def _disconnect_redis_after_test() -> AsyncGenerator[None]:
    yield
    await redis_client.aclose()


async def _seed(slug: str, *, text: str) -> tuple[uuid.UUID, KnowledgeBase]:
    async with get_session() as session:
        org = Organization(name="Caching Test", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Caching WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Caching KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        document = Document(
            tenant_id=org.id,
            knowledge_base_id=knowledge_base.id,
            title="doc.txt",
            storage_key=f"{slug}/doc.txt",
            content_type="text/plain",
            size_bytes=10,
        )
        session.add(document)
        await session.flush()

        chunk = Chunk(tenant_id=org.id, document_id=document.id, text=text, start=0, end=1, index=0)
        session.add(chunk)
        await session.commit()

        return org.id, knowledge_base


@pytest.mark.anyio
async def test_repeated_identical_requests_serve_the_cached_stale_response() -> None:
    """The real proof that Redis is actually being read, not just
    written to and ignored: delete the underlying chunk between the
    two calls -- if the second response still shows it, that data
    could only have come from the cache."""
    tenant_id, knowledge_base = await _seed("cache-stale", text="refund policy allows returns")
    body = ContextSearchRequest(query="refund policy", strategy="keyword")

    with patch.object(settings, "environment", "production"):
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            first = await build_search_context(body, session, tenant_id, knowledge_base)
        assert len(first) == 1

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            result = await session.execute(select(Chunk).where(Chunk.tenant_id == tenant_id))
            for chunk in result.scalars().all():
                await session.delete(chunk)
            await session.commit()

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            second = await build_search_context(body, session, tenant_id, knowledge_base)

        assert second == first


@pytest.mark.anyio
async def test_a_different_query_is_not_served_from_the_others_cache_entry() -> None:
    tenant_id, knowledge_base = await _seed("cache-diff-query", text="refund policy allows returns")

    with patch.object(settings, "environment", "production"):
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            first = await build_search_context(
                ContextSearchRequest(query="refund policy", strategy="keyword"),
                session,
                tenant_id,
                knowledge_base,
            )
        assert len(first) == 1

        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            second = await build_search_context(
                ContextSearchRequest(query="completely unrelated term", strategy="keyword"),
                session,
                tenant_id,
                knowledge_base,
            )
        assert second == []


@pytest.mark.anyio
async def test_cache_is_scoped_per_tenant_even_for_the_identical_query() -> None:
    """Roadmap step 134's own wording: "tenant-scoped" caching."""
    tenant_a, kb_a = await _seed("cache-tenant-a", text="refund policy in tenant a")
    tenant_b, kb_b = await _seed("cache-tenant-b", text="refund policy in tenant b")
    body = ContextSearchRequest(query="refund policy", strategy="keyword")

    with patch.object(settings, "environment", "production"):
        async with get_session() as session:
            await set_tenant_context(session, tenant_a)
            result_a = await build_search_context(body, session, tenant_a, kb_a)

        async with get_session() as session:
            await set_tenant_context(session, tenant_b)
            result_b = await build_search_context(body, session, tenant_b, kb_b)

    assert result_a[0].text == "refund policy in tenant a"
    assert result_b[0].text == "refund policy in tenant b"
