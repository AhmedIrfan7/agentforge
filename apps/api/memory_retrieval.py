"""Identity-based memory retrieval on conversation start (roadmap step
166, AGENTS.md's own "PERSONALIZED EXPERIENCE"/"PERSONALIZED MEMORY"
sections: "When a user provides identifying information... the system
should intelligently retrieve previous interactions... Relevant
long-term memories.").

No Conversation/ConversationSession model or "start a conversation"
endpoint exists yet (Milestone 6) -- there is no real HTTP entry point
to attach this to today. This is the real, tested retrieval logic
itself: given a real, already-authenticated identity (`tenant_id` +
`user_id` -- the only two identity signals this codebase's real auth
system, Milestone 2, actually provides), combine the two real,
already-built long-term memory scopes a starting conversation should
draw on -- user memory (this person's own preferences/history) and
organization memory (shared business context) -- via
`repositories/memory.py:MemoryRepository.list_for_user`/
`list_for_organization` (164), each already ordered by
`importance_score` descending. Session-scoped memory is deliberately
excluded: a NEW conversation has no prior `session_id` of its own yet
to look up (that's what "conversation start" means) -- there is
nothing real to retrieve for that scope here.

`min_importance` defaults to `agents/memory.py:RETENTION_THRESHOLD`
(165) -- the same real bar the Memory Agent itself uses to decide
something was worth keeping in the first place, so retrieval and
retention share one honest definition of "important enough," not two
independently invented thresholds.

Each scope is queried up to `limit` and the combined result is
re-sorted and truncated to `limit` -- a caller asking for the top 20
most relevant memories gets exactly that across both scopes together,
not up to 40 (20 per scope) or an arbitrary per-scope split.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from agents.memory import RETENTION_THRESHOLD
from models.memory import Memory
from repositories.memory import MemoryRepository


async def retrieve_memory_for_conversation_start(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    min_importance: float = RETENTION_THRESHOLD,
    limit: int = 20,
) -> Sequence[Memory]:
    repo = MemoryRepository(session, tenant_id)
    user_memories = await repo.list_for_user(user_id, min_importance=min_importance, limit=limit)
    org_memories = await repo.list_for_organization(min_importance=min_importance, limit=limit)

    combined = [*user_memories, *org_memories]
    combined.sort(key=lambda memory: memory.importance_score, reverse=True)
    return combined[:limit]
