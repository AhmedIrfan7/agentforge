"""Message embedding generation (roadmap step 183, Milestone 6) --
computes `models/message.py:Message.embedding` asynchronously, the
same "chunk exists before its embedding does" shape `embeddings_
pipeline.py` already established for `Chunk`, scaled down to one
message instead of a batch: a message is created and returned to the
caller the instant it's written (message-send's own real response
contract, unaffected by embedding latency), and becomes semantically
searchable once this task actually runs.

Dispatched (`.delay()`) right after EVERY `Message.create()` in
`routers/conversation.py` -- both the user's turn and the assistant's
reply, since `conversation_state.py`'s own conversation search needs
to find either kind of turn. Same "one stage's success dispatches the
next" shape `upload_document`/`extraction.py`'s own dispatch chain
already established.

`_embedding_provider` is its own module-level `OpenAIEmbeddingProvider()`
singleton -- `routers/conversation.py`'s own semantic-search endpoint
constructs a separate instance for computing a QUERY embedding at
request time, same "each consuming module gets its own singleton
instance" pattern `routers/retrieval.py`'s `_retriever_agent` and this
codebase's other `OpenAIEmbeddingProvider()`/`OpenAIProvider()`
singletons already established -- the provider is cheap to construct
and holds no per-caller state worth sharing.
"""

import asyncio
import uuid
from typing import Any

from celery_app import celery_app
from db import get_worker_session, set_tenant_context
from embeddings.base import EmbeddingProvider
from embeddings.openai import OpenAIEmbeddingProvider
from repositories.message import MessageRepository

_embedding_provider: EmbeddingProvider = OpenAIEmbeddingProvider()


async def _run_message_embedding(message_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    async with get_worker_session() as session:
        await set_tenant_context(session, tenant_id)
        repo = MessageRepository(session, tenant_id)
        message = await repo.get(message_id)
        if message is None:
            raise ValueError(f"message {message_id} does not exist")

        vectors = await _embedding_provider.embed([message.content])
        message.embedding = vectors[0]
        await session.commit()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="dispatch_message_embedding",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def dispatch_message_embedding(self: Any, message_id: str, tenant_id: str) -> None:
    asyncio.run(_run_message_embedding(uuid.UUID(message_id), uuid.UUID(tenant_id)))
