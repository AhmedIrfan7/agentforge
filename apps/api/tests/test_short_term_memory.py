"""Tests for short_term_memory.py (roadmap step 163). Calls the module
directly against real Redis -- same isolation pattern
test_rate_limit.py already established for a standalone Redis-backed
module (redis_client.py's connection pool binds to whichever event
loop first uses it, so every test here explicitly disconnects
afterward rather than letting it survive stale into a later test's
different loop).
"""

import uuid
from collections.abc import AsyncGenerator

import pytest

import short_term_memory
from llm.base import Message
from redis_client import redis_client


@pytest.fixture(autouse=True)
async def _disconnect_redis_after_test() -> AsyncGenerator[None]:
    yield
    await redis_client.aclose()


@pytest.mark.anyio
async def test_append_and_get_recent_turns_round_trips_in_order() -> None:
    session_id = uuid.uuid4()

    await short_term_memory.append_turn(session_id, Message(role="user", content="hi"))
    await short_term_memory.append_turn(session_id, Message(role="assistant", content="hello"))

    turns = await short_term_memory.get_recent_turns(session_id)

    assert turns == [
        Message(role="user", content="hi"),
        Message(role="assistant", content="hello"),
    ]


@pytest.mark.anyio
async def test_get_recent_turns_on_an_untouched_session_returns_empty_list() -> None:
    turns = await short_term_memory.get_recent_turns(uuid.uuid4())

    assert turns == []


@pytest.mark.anyio
async def test_sessions_are_isolated_from_each_other() -> None:
    session_a = uuid.uuid4()
    session_b = uuid.uuid4()

    await short_term_memory.append_turn(session_a, Message(role="user", content="a's message"))

    assert await short_term_memory.get_recent_turns(session_a) == [
        Message(role="user", content="a's message")
    ]
    assert await short_term_memory.get_recent_turns(session_b) == []


@pytest.mark.anyio
async def test_max_entries_trims_the_oldest_turns() -> None:
    session_id = uuid.uuid4()

    for i in range(short_term_memory.MAX_ENTRIES + 5):
        await short_term_memory.append_turn(session_id, Message(role="user", content=str(i)))

    turns = await short_term_memory.get_recent_turns(session_id)

    assert len(turns) == short_term_memory.MAX_ENTRIES
    # The oldest 5 (0-4) were trimmed; the window keeps the most recent
    # MAX_ENTRIES, in original append order.
    assert turns[0].content == "5"
    assert turns[-1].content == str(short_term_memory.MAX_ENTRIES + 4)


@pytest.mark.anyio
async def test_append_turn_sets_a_real_ttl() -> None:
    session_id = uuid.uuid4()

    await short_term_memory.append_turn(
        session_id, Message(role="user", content="hi"), ttl_seconds=120
    )

    ttl = await redis_client.ttl(short_term_memory._key(session_id))
    assert 0 < ttl <= 120


@pytest.mark.anyio
async def test_clear_removes_all_turns() -> None:
    session_id = uuid.uuid4()
    await short_term_memory.append_turn(session_id, Message(role="user", content="hi"))

    await short_term_memory.clear(session_id)

    assert await short_term_memory.get_recent_turns(session_id) == []
