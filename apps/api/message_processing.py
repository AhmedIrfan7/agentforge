"""Shared "process one conversation turn" logic (roadmap step 192).

Promoted out of `routers/conversation.py`'s own body -- where it lived
correctly, as an internal helper, from steps 179/187 through 191 --
once `routers/public_conversation.py` (step 192's own anonymous
message-send) became a second real caller. A router importing a
helper out of ANOTHER router module would be backwards (routers are
meant to sit at the top of this codebase's import graph, not be
depended on by each other), so this lives in its own neutral module
instead, the same way `citations.py`/`context_builder.py` already sit
below every router that uses them.

`citation_json`/`build_citations_for_result` are the exact same real
logic step 187 built -- citations.py's own module docstring already
explains why it stays DB-free and expects a caller-supplied
`document_info` lookup; this is that caller, unchanged.

`generate_assistant_reply` does NOT write an audit log entry or build
a `MessageRead` response -- callers differ there for real reasons (an
anonymous caller has no `actor_user_id` to log; `send_message_
streaming` builds its own SSE response instead of a plain
`MessageRead`), so those stay each caller's own job.
`send_message_streaming` is deliberately NOT built on top of this
helper -- its own generator/session-lifecycle concerns (see routers/
conversation.py's own docstring on why touching the ORM object from
inside that generator is unsafe) are enough of a distinct shape that
folding it in here would obscure both, not simplify either.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from citations import Citation, DocumentInfo, build_citations
from context_builder import ContextChunk
from conversation_state import transition
from message_embedding import dispatch_message_embedding
from models.assistant import Assistant
from models.conversation import Conversation
from models.message import Message
from orchestrator import OrchestratorResult, orchestrator
from repositories.document import DocumentRepository
from repositories.knowledge_base import KnowledgeBaseRepository
from repositories.message import MessageRepository
from schemas.message import CitationRead


def citation_json(citation: Citation) -> dict[str, object]:
    return CitationRead(
        chunk_id=citation.chunk_id,
        document_id=citation.document_id,
        document_title=citation.document_title,
        knowledge_base_name=citation.knowledge_base_name,
        section=citation.section,
    ).model_dump(mode="json")


async def build_citations_for_result(
    session: AsyncSession, tenant_id: uuid.UUID, result: OrchestratorResult
) -> list[Citation]:
    if not result.chunks:
        return []

    document_repo = DocumentRepository(session, tenant_id)
    knowledge_base_repo = KnowledgeBaseRepository(session, tenant_id)
    document_info: dict[uuid.UUID, DocumentInfo] = {}
    for chunk in result.chunks:
        if chunk.document_id in document_info:
            continue
        document = await document_repo.get(chunk.document_id)
        if document is None:
            continue
        knowledge_base = await knowledge_base_repo.get(document.knowledge_base_id)
        if knowledge_base is None:
            continue
        document_info[chunk.document_id] = DocumentInfo(
            title=document.title, knowledge_base_name=knowledge_base.name
        )

    context_chunks = [
        ContextChunk(id=chunk.chunk_id, document_id=chunk.document_id, text=chunk.text)
        for chunk in result.chunks
        if chunk.document_id in document_info
    ]
    return build_citations(context_chunks, document_info=document_info)


async def generate_assistant_reply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    assistant: Assistant,
    conversation: Conversation,
    content: str,
) -> Message:
    if conversation.status == "new":
        transition(conversation, "active")

    repo = MessageRepository(session, tenant_id)
    user_message = await repo.create(
        conversation_id=conversation.id,
        role="user",
        content=content,
    )
    dispatch_message_embedding.delay(str(user_message.id), str(tenant_id))

    result = await orchestrator.handle(
        content, tenant_id=tenant_id, knowledge_base_id=assistant.knowledge_base_id
    )
    citations = await build_citations_for_result(session, tenant_id, result)

    assistant_message = await repo.create(
        conversation_id=conversation.id,
        role="assistant",
        content=result.response,
        citations=[citation_json(c) for c in citations],
    )
    dispatch_message_embedding.delay(str(assistant_message.id), str(tenant_id))
    return assistant_message
