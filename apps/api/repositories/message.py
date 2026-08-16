import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.conversation import Conversation
from models.message import Message
from repositories.base import TenantScopedRepository


@dataclass
class MessageSearchResult:
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    content: str
    score: float


class MessageRepository(TenantScopedRepository[Message]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session, tenant_id, Message)

    async def get_preceding_user_message(
        self, conversation_id: uuid.UUID, *, before: datetime
    ) -> Message | None:
        """Roadmap step 188 -- finds the real user turn that produced a
        given assistant reply, so regenerate_response can re-run the
        orchestrator against the SAME original query rather than
        inventing a new one. Messages alternate user/assistant in this
        codebase's own real flow (every send_message call writes
        exactly one of each, in that order), so the nearest earlier
        user message in the same conversation is unambiguously the
        right one -- no explicit parent/reply-to link needed for a
        shape this simple.

        `<=`, not `<` -- verified live before trusting it: Postgres's
        `now()` (models/mixins.py:TimestampMixin's own `created_at`
        server_default) returns the TRANSACTION's start time, constant
        for its whole duration, not per-statement -- send_message
        writes both messages in one uncommitted transaction, so a
        user/assistant pair's `created_at` values are byte-identical,
        confirmed by a real insert with a real 1-second sleep between
        them. A strict `<` silently found nothing for every real pair.
        `<=` is still safe: the one-user-then-one-assistant-per-call
        invariant guarantees at most one `role="user"` row can ever
        share that exact timestamp."""
        stmt = (
            select(Message)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.conversation_id == conversation_id,
                Message.role == "user",
                Message.created_at <= before,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> Sequence[Message]:
        """Roadmap step 191 -- the full, ordered transcript a real
        export needs; no repository method for this existed before
        this step because nothing needed the WHOLE conversation back
        in order until now (list_conversations/182 returns
        Conversations, not their Messages; search returns individual
        matches, not a transcript)."""
        stmt = (
            select(Message)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_for_voice_session(self, voice_session_id: uuid.UUID) -> Sequence[Message]:
        """Roadmap step 228 -- a real, ordered voice-call transcript,
        scoped by the real `Message.voice_session_id` FK (set by
        `message_processing.py:generate_assistant_reply`'s own optional
        parameter) rather than a `created_at`-time-window
        approximation -- exact by construction, same "a real relational
        link, not a derived guess" reasoning `list_for_conversation`'s
        own precedent doesn't need, since a whole conversation has no
        narrower real scope to approximate in the first place."""
        stmt = (
            select(Message)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.voice_session_id == voice_session_id,
            )
            .order_by(Message.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search_keyword(
        self,
        assistant_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
    ) -> list[MessageSearchResult]:
        """Roadmap step 183 -- Postgres full-text search against
        Message.search_vector, the same query shape (plainto_tsquery/
        ts_rank/@@) repositories/chunk.py:search_by_keyword already
        established for Chunk. Scoped to the caller's OWN conversations
        only (joined through Conversation, filtered by both
        assistant_id and user_id) -- same "conversation history is
        personal" principle routers/conversation.py's own list
        endpoint (182) already established, not a new decision made
        here."""
        ts_query = func.plainto_tsquery("english", query)
        rank = func.ts_rank(Message.search_vector, ts_query).label("rank")
        stmt = (
            select(Message, rank)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.tenant_id == self.tenant_id,
                Conversation.assistant_id == assistant_id,
                Conversation.user_id == user_id,
                Message.search_vector.op("@@")(ts_query),
            )
            .order_by(rank.desc())
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return [
            MessageSearchResult(
                message_id=message.id,
                conversation_id=message.conversation_id,
                content=message.content,
                score=score,
            )
            for message, score in result.all()
        ]

    async def search_semantic(
        self,
        assistant_id: uuid.UUID,
        user_id: uuid.UUID,
        query_vector: list[float],
        *,
        top_k: int = 10,
    ) -> list[MessageSearchResult]:
        """Roadmap step 183 -- cosine-distance search against
        Message.embedding, the same query shape vectorstore/pgvector.
        py:PgVectorStore.search() already established for Chunk.
        Excludes messages with no embedding yet (embedding.is_not(None))
        -- same real, honest, temporary gap Chunk's own dense search
        already documents for a just-created row awaiting its
        embedding task."""
        distance = Message.embedding.cosine_distance(query_vector)
        stmt = (
            select(Message, distance.label("distance"))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.tenant_id == self.tenant_id,
                Conversation.assistant_id == assistant_id,
                Conversation.user_id == user_id,
                Message.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return [
            MessageSearchResult(
                message_id=message.id,
                conversation_id=message.conversation_id,
                content=message.content,
                score=1.0 - dist,
            )
            for message, dist in result.all()
        ]
