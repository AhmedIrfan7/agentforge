"""Tests for message_embedding.py (roadmap step 183) -- exercises
_run_message_embedding directly against real Postgres (same "no mocks
for infrastructure this project owns" reasoning test_embeddings_
pipeline.py already established), with a fake EmbeddingProvider
swapped in via monkeypatch instead of a real OpenAI call.
"""

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from message_embedding import _run_message_embedding
from models.assistant import Assistant
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.message import Message
from models.organization import Organization
from models.workspace import Workspace


@dataclass
class _FakeEmbeddingProvider:
    name: str = "fake"
    dimensions: int = 1536
    call_texts: list[str] | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.call_texts is not None:
            self.call_texts.extend(texts)
        return [[float(len(text))] * self.dimensions for text in texts]


async def _new_message(slug: str, *, content: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with get_session() as session:
        org = Organization(name="Message Embedding Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Embed WS", slug=f"{slug}-ws")
        session.add(workspace)
        await session.flush()

        knowledge_base = KnowledgeBase(
            tenant_id=org.id, workspace_id=workspace.id, name="Embed KB", slug=f"{slug}-kb"
        )
        session.add(knowledge_base)
        await session.flush()

        assistant = Assistant(
            tenant_id=org.id, knowledge_base_id=knowledge_base.id, name="Embed Bot", slug="bot"
        )
        session.add(assistant)
        await session.flush()

        conversation = Conversation(tenant_id=org.id, assistant_id=assistant.id)
        session.add(conversation)
        await session.flush()

        message = Message(
            tenant_id=org.id, conversation_id=conversation.id, role="user", content=content
        )
        session.add(message)
        await session.flush()
        await session.commit()
        return org.id, message.id


@pytest.mark.anyio
async def test_computes_and_stores_a_real_embedding_for_a_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeEmbeddingProvider(call_texts=[])
    monkeypatch.setattr("message_embedding._embedding_provider", fake)

    tenant_id, message_id = await _new_message("msg-embed-basic", content="Hello there")
    await _run_message_embedding(message_id, tenant_id)

    assert fake.call_texts == ["Hello there"]

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one()
        assert message.embedding is not None
        assert len(message.embedding) == 1536


@pytest.mark.anyio
async def test_raises_for_a_nonexistent_message_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("message_embedding._embedding_provider", _FakeEmbeddingProvider())

    tenant_id, _message_id = await _new_message("msg-embed-missing", content="irrelevant")
    with pytest.raises(ValueError, match="does not exist"):
        await _run_message_embedding(uuid.uuid4(), tenant_id)
