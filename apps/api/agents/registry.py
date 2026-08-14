"""Agent Registry (roadmap step 139, AGENTS.md SECTION 5) -- the real
register/discover/health-check machinery `agents/__init__.py`'s own
docstring has been deferring since step 095 ("build that machinery
when something actually needs to choose between agents at runtime,
not before"). LangGraph (137) plus the real `run()`/`config` contract
(138) are that real need: an Orchestrator (step 140) needs to look
agents up by name and invoke them generically, not import each one
directly.

Starts with nothing pre-registered: none of the three existing
concrete agents (`DocumentAnalysisAgent`, `ChunkingRecommendationAgent`,
`RetrieverAgent`) implement `run()` (`agents/base.py`'s own step-138
docstring explains why they weren't retrofitted) -- registering an
agent this registry can't actually invoke through its own real
contract would be dishonest machinery pretending to more capability
than exists. Real registrations start once a real `run()`-implementing
agent exists (steps 144+).

`register()` does NOT reject an agent whose `run()` isn't implemented
-- registration and health are deliberately separate operations, the
same way a real service registry lets something register before it's
ready and reports readiness separately, rather than refusing entry
outright. `health_check()` is deliberately narrow and honest about
what's actually checkable today: no LLM/network-dependent agent exists
in this registry yet (nothing here calls OpenAI/Anthropic), so it
can't be a genuine liveness probe against an external dependency --
instead it reports whether each agent's own `run()` was actually
overridden (`type(agent).run is not Agent.run`) rather than left as
the base class's `NotImplementedError` stub, a real, checkable signal
for "would invoking this agent right now have any chance of working."

Duplicate registration and lookup of an unregistered name both raise
(`AgentAlreadyRegisteredError`/`AgentNotFoundError`) rather than
silently overwriting or returning `None` -- same "fail loud on a
caller bug" precedent `citations.py`/`vectorstore/pgvector.py:
PgVectorStore.upsert()` already established.

`agent_registry` is a module-level singleton for real app-wide use
(the same shape `redis_client.py`/`routers/retrieval.py`'s own
`_retriever_agent` already use) -- tests construct their own fresh
`AgentRegistry()` instances instead, to avoid cross-test pollution of
shared global state.
"""

from typing import Any

from agents.base import Agent


class AgentAlreadyRegisteredError(Exception):
    pass


class AgentNotFoundError(Exception):
    pass


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent[Any, Any]] = {}

    def register(self, agent: Agent[Any, Any]) -> None:
        if agent.name in self._agents:
            raise AgentAlreadyRegisteredError(
                f"an agent named {agent.name!r} is already registered"
            )
        self._agents[agent.name] = agent

    def get(self, name: str) -> Agent[Any, Any]:
        try:
            return self._agents[name]
        except KeyError:
            raise AgentNotFoundError(f"no agent named {name!r} is registered") from None

    def discover(self) -> list[str]:
        return sorted(self._agents)

    def health_check(self) -> dict[str, bool]:
        return {name: type(agent).run is not Agent.run for name, agent in self._agents.items()}


agent_registry = AgentRegistry()
