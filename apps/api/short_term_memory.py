"""Redis-backed short-term memory store (roadmap step 163, Milestone
5) -- conversation-scoped, ephemeral "active conversation context"
(AGENTS.md's own "MEMORY REQUIREMENTS": "Short-Term Memory. Maintains
active conversation context."). Genuinely separate from
`models/memory.py:Memory` (162), which is the long-term, Postgres-
backed half -- short-term entries never touch that table; the two only
meet once step 165's Memory Agent logic decides something here
deserves promotion to long-term retention.

Uses `redis_client.py`'s shared client directly, the same pattern
`rate_limit.py` (Redis-backed fixed-window limiting) and
`routers/retrieval.py`'s own context cache already established -- one
process-wide connection pool, no new client.

A Redis LIST per conversation (`RPUSH`/`LTRIM`/`LRANGE`), not a single
JSON blob: "maintains active conversation context" means a bounded,
ordered recent-turn window, which a list gives for free (append, trim
to a max length, read back in order) with per-command atomicity a
read-modify-write blob cycle wouldn't have under concurrent writers.
Entries are `llm.base.Message` (role/content) -- the exact shape a
real chat call will eventually need to reconstruct a prompt, not a
parallel dataclass reinventing the same two fields. `session_id` is
the same identifier `models/memory.py:Memory.session_id` uses -- that
column gained a real foreign key to `models/conversation.py:Conversation`
at step 176; this one stays a plain UUID regardless, since Redis keys
have no foreign-key concept to enforce one against.

Each write refreshes the key's TTL (`DEFAULT_TTL_SECONDS`, one hour) --
genuinely short-term: an idle conversation's working memory should
expire on its own, unlike anything promoted into long-term storage.
`MAX_ENTRIES` bounds the list length (`LTRIM` after every push) so an
unusually long-running conversation can't grow this unboundedly before
its TTL catches up.

No environment-gating in this module itself, unlike `rate_limit.py`'s
FastAPI-facing dependency wrapper -- nothing here is wired into an
HTTP request path yet (no endpoint asked for by this step), so there's
no `TestClient`-driven test suite to protect from Redis's known
event-loop-binding-under-pytest issue; tests call these functions
directly against real Redis with their own explicit disconnect-after-
test cleanup, the same isolation `test_rate_limit.py` already
established.
"""

import json
import uuid

from llm.base import Message
from redis_client import redis_client

DEFAULT_TTL_SECONDS = 60 * 60  # one hour of conversation inactivity
MAX_ENTRIES = 50


def _key(session_id: uuid.UUID) -> str:
    return f"short_term_memory:{session_id}"


async def append_turn(
    session_id: uuid.UUID, message: Message, *, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> None:
    key = _key(session_id)
    payload = json.dumps({"role": message.role, "content": message.content})
    await redis_client.rpush(key, payload)
    await redis_client.ltrim(key, -MAX_ENTRIES, -1)
    await redis_client.expire(key, ttl_seconds)


async def get_recent_turns(session_id: uuid.UUID) -> list[Message]:
    raw_entries = await redis_client.lrange(_key(session_id), 0, -1)
    return [
        Message(role=entry["role"], content=entry["content"])
        for entry in (json.loads(raw) for raw in raw_entries)
    ]


async def clear(session_id: uuid.UUID) -> None:
    await redis_client.delete(_key(session_id))
