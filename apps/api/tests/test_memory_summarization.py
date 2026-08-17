"""Tests for memory_summarization.py (roadmap step 167). Covers the
real "no key configured" failure path against the actual
api.openai.com endpoint (same discipline test_openai_llm_provider.py
already established -- LLMProviderError is a real, live-verified
failure mode, not assumed), plus the full success/not-retained paths
using httpx.MockTransport (same technique test_openai_llm_provider.py
uses for everything beyond the live failure probe).
"""

import json
import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
import structlog.testing
from sqlalchemy import select

from db import get_session, set_tenant_context
from llm.base import LLMProviderError, Message
from memory_summarization import _run_memory_summarization
from models.assistant import Assistant
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.memory import Memory
from models.organization import Organization
from models.workspace import Workspace
from redis_client import redis_client
from repositories.memory import MemoryRepository
from short_term_memory import append_turn, get_recent_turns


async def _new_org(slug: str) -> uuid.UUID:
    async with get_session() as session:
        org = Organization(name="Memory Summarization Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await session.commit()
        return org.id


async def _new_conversation(tenant_id: uuid.UUID, slug: str) -> uuid.UUID:
    # session_id has a real FK to Conversation as of step 176 -- any test
    # here that actually persists a Memory row (not just Redis turns)
    # needs a genuine one, unlike the Redis-only tests in this file which
    # never touch Postgres for their session_id.
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        workspace = Workspace(tenant_id=tenant_id, name="Mem Summ WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=tenant_id, workspace_id=workspace.id, name="Mem Summ KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        assistant = Assistant(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base.id,
            name="Mem Summ Bot",
            slug="bot",
        )
        session.add(assistant)
        await session.flush()

        conversation = Conversation(tenant_id=tenant_id, assistant_id=assistant.id)
        session.add(conversation)
        await session.flush()
        await session.commit()
        return conversation.id


def _client_factory(handler: httpx.MockTransport) -> type[httpx.AsyncClient]:
    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = handler
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    return _PatchedClient


def _mock_completion_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


@pytest.fixture(autouse=True)
async def _disconnect_redis_after_test() -> AsyncGenerator[None]:
    yield
    await redis_client.aclose()


@pytest.mark.anyio
async def test_does_nothing_when_no_short_term_memory_exists() -> None:
    tenant_id = await _new_org("mem-summ-empty")
    session_id = uuid.uuid4()

    # No API key configured in this environment -- if this reached the
    # LLM call it would raise. Reaching the end without error proves
    # the early return for an untouched session works.
    await _run_memory_summarization(session_id, tenant_id)


@pytest.mark.anyio
async def test_raises_the_real_provider_error_against_the_live_api_with_no_key() -> None:
    tenant_id = await _new_org("mem-summ-live-fail")
    session_id = uuid.uuid4()
    await append_turn(session_id, Message(role="user", content="My name is Jordan."))

    with pytest.raises(LLMProviderError):
        await _run_memory_summarization(session_id, tenant_id)

    # Nothing cleared on failure -- a retry should see the same turns.
    assert await get_recent_turns(session_id) != []


@pytest.mark.anyio
async def test_a_retainable_summary_is_written_as_a_session_scoped_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = await _new_org("mem-summ-retain")
    session_id = await _new_conversation(tenant_id, "mem-summ-retain")
    await append_turn(session_id, Message(role="user", content="My name is Jordan."))

    # MemoryAgent's real retention signal phrases (165) are first-person
    # ("my name is", "remember that", ...), matching raw conversational
    # turns -- an LLM-generated summary is naturally third-person, so
    # this mock deliberately includes a matching phrase to exercise the
    # real "retained" path rather than asserting a heuristic mismatch.
    summary_text = "Remember that Jordan prefers email over chat."

    def handler(request: httpx.Request) -> httpx.Response:
        return _mock_completion_response(summary_text)

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )

    with structlog.testing.capture_logs() as logs:
        await _run_memory_summarization(session_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        memory = result.scalar_one()
        assert memory.scope == "session"
        assert memory.session_id == session_id
        assert memory.content == summary_text
        assert memory.importance_score == 0.9

    # Short-term memory is cleared after a successful summarization.
    assert await get_recent_turns(session_id) == []

    lifecycle_events = [e for e in logs if e["event"] == "memory_lifecycle"]
    assert len(lifecycle_events) == 1
    assert lifecycle_events[0]["outcome"] == "created"
    assert lifecycle_events[0]["reason"] == "contains an explicit identity or preference signal"


@pytest.mark.anyio
async def test_a_low_value_summary_is_not_retained_but_short_term_memory_still_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = await _new_org("mem-summ-skip")
    session_id = uuid.uuid4()
    await append_turn(session_id, Message(role="user", content="Just saying hi."))

    def handler(request: httpx.Request) -> httpx.Response:
        return _mock_completion_response("They said hello.")

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )

    with structlog.testing.capture_logs() as logs:
        await _run_memory_summarization(session_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        assert result.scalars().all() == []

    assert await get_recent_turns(session_id) == []

    lifecycle_events = [e for e in logs if e["event"] == "memory_lifecycle"]
    assert len(lifecycle_events) == 1
    assert lifecycle_events[0]["outcome"] == "ignored"


@pytest.mark.anyio
async def test_a_higher_importance_conflicting_summary_updates_the_existing_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = await _new_org("mem-summ-conflict-update")
    session_id = await _new_conversation(tenant_id, "mem-summ-conflict-update")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        existing = await repo.create(
            scope="session",
            session_id=session_id,
            content="Jordan prefers email over chat.",
            importance_score=0.4,
        )
        await session.commit()
        existing_id = existing.id

    await append_turn(session_id, Message(role="user", content="My name is Jordan."))
    summary_text = "Remember that Jordan prefers email over chat."

    def handler(request: httpx.Request) -> httpx.Response:
        return _mock_completion_response(summary_text)

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )

    with structlog.testing.capture_logs() as logs:
        await _run_memory_summarization(session_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        memories = result.scalars().all()
        # Still one row -- the conflicting memory was updated, not
        # duplicated.
        assert len(memories) == 1
        assert memories[0].id == existing_id
        assert memories[0].content == summary_text
        assert memories[0].importance_score == 0.9

    lifecycle_events = [e for e in logs if e["event"] == "memory_lifecycle"]
    assert lifecycle_events[0]["outcome"] == "updated"


@pytest.mark.anyio
async def test_a_lower_importance_conflicting_summary_is_ignored_and_leaves_existing_memory_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = await _new_org("mem-summ-conflict-ignore")
    session_id = await _new_conversation(tenant_id, "mem-summ-conflict-ignore")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MemoryRepository(session, tenant_id)
        # 0.95 -- deliberately higher than any score MemoryAgent's own
        # three-tier heuristic (165) can ever produce (max 0.9), the
        # same way a manually curated/promoted memory could genuinely
        # end up scored -- so a real, retained (>= RETENTION_THRESHOLD)
        # new summary can still lose the conflict comparison.
        await repo.create(
            scope="session",
            session_id=session_id,
            content="Jordan works in the EU timezone.",
            importance_score=0.95,
        )
        await session.commit()

    await append_turn(session_id, Message(role="user", content="What timezone am I in?"))
    # Contains a signal phrase (scores 0.9, clears RETENTION_THRESHOLD
    # so it reaches the conflict-check branch at all) and overlaps
    # with the existing memory's content -- but 0.9 < 0.95.
    summary_text = "Remember that Jordan works in the EU timezone."

    def handler(request: httpx.Request) -> httpx.Response:
        return _mock_completion_response(summary_text)

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )

    with structlog.testing.capture_logs() as logs:
        await _run_memory_summarization(session_id, tenant_id)

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        memories = result.scalars().all()
        assert len(memories) == 1
        assert memories[0].content == "Jordan works in the EU timezone."
        assert memories[0].importance_score == 0.95

    lifecycle_events = [e for e in logs if e["event"] == "memory_lifecycle"]
    assert lifecycle_events[0]["outcome"] == "ignored"
    assert "conflict" in lifecycle_events[0]["reason"]


@pytest.mark.anyio
async def test_sends_the_real_conversation_turns_alongside_a_summarization_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = await _new_org("mem-summ-prompt")
    session_id = uuid.uuid4()
    await append_turn(session_id, Message(role="user", content="My name is Jordan."))
    await append_turn(session_id, Message(role="assistant", content="Nice to meet you, Jordan."))

    seen_messages: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        seen_messages.extend(payload["messages"])
        return _mock_completion_response("Summary.")

    monkeypatch.setattr(
        "llm.openai.httpx.AsyncClient", _client_factory(httpx.MockTransport(handler))
    )

    await _run_memory_summarization(session_id, tenant_id)

    assert seen_messages[0]["role"] == "system"
    assert seen_messages[1] == {"role": "user", "content": "My name is Jordan."}
    # As of step 251, a stored assistant turn is wrapped in explicit
    # <retrieved_content> delimiters before it reaches this real LLM
    # call (agents/safety.py:SafetyAgent) -- user turns pass through
    # unwrapped, only the assistant turn changes shape here.
    assert seen_messages[2]["role"] == "assistant"
    assert seen_messages[2]["content"] == (
        "<retrieved_content>\nNice to meet you, Jordan.\n</retrieved_content>"
    )
