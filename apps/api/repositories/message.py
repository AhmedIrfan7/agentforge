import uuid
from dataclasses import dataclass

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
