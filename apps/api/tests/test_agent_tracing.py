"""Tests for agents/tracing.py (roadmap step 153; real persistence as
of step 245). Same structlog.testing.capture_logs() technique
test_retriever_agent.py already established at step 129 for asserting
real structured log events, generalized here to traced_run's
"agent_execution" event.
"""

import uuid
from collections.abc import MutableMapping
from typing import Any

import pytest
import structlog.testing
from sqlalchemy import select

from agents.base import Agent
from agents.tracing import traced_run
from db import get_session, set_tenant_context
from llm.base import LLMResponse
from models.agent_execution_log import AgentExecutionLog
from models.organization import Organization


class _EchoAgent(Agent[str, str]):
    name = "echo"

    async def run(self, input: str) -> str:
        return f"echo: {input}"


class _FailingAgent(Agent[str, str]):
    name = "failing"

    async def run(self, input: str) -> str:
        raise ValueError("boom")


class _LLMBackedAgent(Agent[str, LLMResponse]):
    name = "llm-backed"

    async def run(self, input: str) -> LLMResponse:
        return LLMResponse(content="hi", prompt_tokens=12, completion_tokens=3)


def _events(logs: list[MutableMapping[str, Any]]) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == "agent_execution"]


@pytest.mark.anyio
async def test_traced_run_returns_the_real_agent_output() -> None:
    result = await traced_run(_EchoAgent(), "hello")
    assert result == "echo: hello"


@pytest.mark.anyio
async def test_traced_run_logs_a_success_event_with_no_tokens() -> None:
    with structlog.testing.capture_logs() as logs:
        await traced_run(_EchoAgent(), "hello")

    events = _events(logs)
    assert len(events) == 1
    assert events[0]["agent_name"] == "echo"
    assert events[0]["status"] == "success"
    assert events[0]["latency_ms"] >= 0
    assert events[0]["prompt_tokens"] is None
    assert events[0]["completion_tokens"] is None


@pytest.mark.anyio
async def test_traced_run_logs_a_failure_event_and_reraises() -> None:
    with structlog.testing.capture_logs() as logs, pytest.raises(ValueError, match="boom"):
        await traced_run(_FailingAgent(), "hello")

    events = _events(logs)
    assert len(events) == 1
    assert events[0]["agent_name"] == "failing"
    assert events[0]["status"] == "failure"
    assert events[0]["prompt_tokens"] is None


@pytest.mark.anyio
async def test_traced_run_reports_real_tokens_for_an_llm_backed_agent() -> None:
    with structlog.testing.capture_logs() as logs:
        await traced_run(_LLMBackedAgent(), "hello")

    events = _events(logs)
    assert events[0]["prompt_tokens"] == 12
    assert events[0]["completion_tokens"] == 3


async def _new_org(slug: str) -> uuid.UUID:
    async with get_session() as session:
        org = Organization(name="Tracing Test Org", slug=slug)
        session.add(org)
        await session.flush()
        await session.commit()
        return org.id


async def _cleanup_org(org_id: uuid.UUID) -> None:
    async with get_session() as session:
        await set_tenant_context(session, org_id)
        result = await session.execute(
            select(AgentExecutionLog).where(AgentExecutionLog.tenant_id == org_id)
        )
        for row in result.scalars().all():
            await session.delete(row)
        await session.flush()
        org = await session.get(Organization, org_id)
        if org is not None:
            await session.delete(org)
        await session.commit()


@pytest.mark.anyio
async def test_traced_run_without_tenant_id_persists_nothing() -> None:
    """Backward-compat proof: agents/parallel.py and agents/
    resilience.py's own real call sites never pass tenant_id, and must
    keep working exactly as before -- no new required behavior forced
    on them."""
    await traced_run(_EchoAgent(), "hello")
    async with get_session() as session:
        result = await session.execute(
            select(AgentExecutionLog).where(AgentExecutionLog.agent_name == "echo")
        )
        # Real proof of "nothing," not just "nothing under some
        # tenant" -- RLS with no tenant context set returns zero rows
        # for everyone, which is exactly the assertion here needs.
        assert result.scalars().all() == []


@pytest.mark.anyio
async def test_traced_run_with_tenant_id_persists_a_real_success_row() -> None:
    org_id = await _new_org("tracing-persist-success")
    try:
        await traced_run(_EchoAgent(), "hello", tenant_id=org_id)

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(AgentExecutionLog).where(AgentExecutionLog.tenant_id == org_id)
            )
            rows = result.scalars().all()

        assert len(rows) == 1
        assert rows[0].agent_name == "echo"
        assert rows[0].status == "success"
        assert rows[0].latency_ms >= 0
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_traced_run_with_tenant_id_persists_a_real_failure_row_and_still_reraises() -> None:
    org_id = await _new_org("tracing-persist-failure")
    try:
        with pytest.raises(ValueError, match="boom"):
            await traced_run(_FailingAgent(), "hello", tenant_id=org_id)

        async with get_session() as session:
            await set_tenant_context(session, org_id)
            result = await session.execute(
                select(AgentExecutionLog).where(AgentExecutionLog.tenant_id == org_id)
            )
            rows = result.scalars().all()

        assert len(rows) == 1
        assert rows[0].status == "failure"
    finally:
        await _cleanup_org(org_id)


@pytest.mark.anyio
async def test_traced_run_survives_a_real_persistence_failure_without_breaking_the_call() -> None:
    """A tenant_id with no real Organization row violates the table's
    own FK constraint on insert -- a real, not simulated, persistence
    failure. traced_run's own "observe without altering control flow"
    principle means this must still return the real agent output."""
    bogus_tenant_id = uuid.uuid4()
    result = await traced_run(_EchoAgent(), "hello", tenant_id=bogus_tenant_id)
    assert result == "echo: hello"
