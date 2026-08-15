"""Model-only test (roadmap step 162) -- no repository or Memory Agent
logic exists yet (that's steps 164-165's job). Exercises the ORM/RLS
layer directly, since there's no router to go through, same precedent
test_chunk_model.py/test_assistant_model.py already established.
"""

import uuid

import pytest
from sqlalchemy import select

from db import get_session, set_tenant_context
from models.memory import Memory
from models.organization import Organization
from models.user import User


async def _new_org(slug: str) -> uuid.UUID:
    async with get_session() as session:
        org = Organization(name="Memory Test Org", slug=f"{slug}-org")
        session.add(org)
        await session.flush()
        await session.commit()
        return org.id


async def _new_user(email: str) -> uuid.UUID:
    async with get_session() as session:
        user = User(email=email, full_name="Memory Test User")
        session.add(user)
        await session.flush()
        await session.commit()
        return user.id


async def _cleanup_user(user_id: uuid.UUID) -> None:
    # users is global, not tenant-scoped -- the org-slug cleanup every
    # other model test here relies on (an external DELETE FROM
    # organizations before an authoritative run) never touches it, so
    # any test that creates a User directly must clean it up itself or
    # its fixed email collides with ix_users_email on the next run.
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
            await session.commit()


@pytest.mark.anyio
async def test_create_and_read_organization_scoped_memory() -> None:
    tenant_id = await _new_org("mem-org-scope")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        memory = Memory(
            tenant_id=tenant_id,
            scope="organization",
            content="This org prefers formal responses.",
        )
        session.add(memory)
        await session.flush()

        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        fetched = result.scalar_one()
        assert fetched.scope == "organization"
        assert fetched.content == "This org prefers formal responses."
        assert fetched.user_id is None
        assert fetched.session_id is None
        # Real default -- only "long_term" is ever written by real code
        # today (163's short-term store is entirely Redis-based).
        assert fetched.memory_type == "long_term"


@pytest.mark.anyio
async def test_create_and_read_user_scoped_memory() -> None:
    tenant_id = await _new_org("mem-user-scope")
    user_id = await _new_user("mem-user-scope@example.com")
    try:
        async with get_session() as session:
            await set_tenant_context(session, tenant_id)
            memory = Memory(
                tenant_id=tenant_id,
                scope="user",
                user_id=user_id,
                content="Prefers email over chat.",
            )
            session.add(memory)
            await session.flush()

            result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
            fetched = result.scalar_one()
            assert fetched.scope == "user"
            assert fetched.user_id == user_id
    finally:
        await _cleanup_user(user_id)


@pytest.mark.anyio
async def test_create_and_read_session_scoped_memory_with_an_unconstrained_session_id() -> None:
    """session_id has no foreign key -- no Conversation/ConversationSession
    model exists yet (Milestone 6), so any UUID is accepted here."""
    tenant_id = await _new_org("mem-session-scope")
    fake_session_id = uuid.uuid4()
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        memory = Memory(
            tenant_id=tenant_id,
            scope="session",
            session_id=fake_session_id,
            content="Asked about refund policy earlier in this conversation.",
        )
        session.add(memory)
        await session.flush()

        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        fetched = result.scalar_one()
        assert fetched.scope == "session"
        assert fetched.session_id == fake_session_id


@pytest.mark.anyio
async def test_deleting_the_organization_cascades_to_its_memories() -> None:
    tenant_id = await _new_org("mem-cascade-org")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(Memory(tenant_id=tenant_id, scope="organization", content="A fact."))
        await session.commit()

    async with get_session() as session:
        org = await session.get(Organization, tenant_id)
        assert org is not None
        await session.delete(org)
        await session.commit()

    async with get_session() as session:
        # RLS hides every row with no tenant context set, regardless of
        # whether cascade actually happened -- set it explicitly so an
        # empty result here really does prove cascade-delete, not just
        # RLS filtering everything out by default.
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        assert result.scalars().all() == []


@pytest.mark.anyio
async def test_deleting_the_user_cascades_to_their_memories() -> None:
    tenant_id = await _new_org("mem-cascade-user")
    user_id = await _new_user("mem-cascade-user@example.com")
    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        session.add(
            Memory(tenant_id=tenant_id, scope="user", user_id=user_id, content="A preference.")
        )
        await session.commit()

    async with get_session() as session:
        user = await session.get(User, user_id)
        assert user is not None
        await session.delete(user)
        await session.commit()

    async with get_session() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(select(Memory).where(Memory.tenant_id == tenant_id))
        assert result.scalars().all() == []
