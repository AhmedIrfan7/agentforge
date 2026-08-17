"""Local dev seed script — demo org/workspace/user, for a fresh clone to
have something to look at immediately. Idempotent: safe to run repeatedly,
skips anything that already exists rather than erroring.

Roadmap step 291 extended this with a real demo knowledge base, a real
demo document (pushed through the actual upload pipeline --
antivirus.py -> storage.py -> DocumentRepository -> extraction.py's
dispatch_extraction, the same path routers/document.py:upload_document
uses -- not hand-inserted rows that would skip real validation), and a
real demo Assistant configured against it, so a fresh clone has an
actual working example of the retrieval/RAG shape to look at, not just
an empty org shell. This only works end to end if a Celery worker is
also running (`make worker-dev`) -- exactly the same real requirement
any user's own first document upload has; the demo document isn't a
special case that bypasses it.

Usage: uv run python -m scripts.seed  (from apps/api)
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.configuration import AgentConfiguration
from antivirus import scan_for_viruses
from auth.passwords import hash_password
from db import get_session, set_tenant_context
from extraction import dispatch_extraction
from logging_config import configure_logging, get_logger
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.user import User
from models.workspace import Workspace
from repositories.assistant import AssistantRepository
from repositories.document import DocumentRepository
from repositories.knowledge_base import KnowledgeBaseRepository
from storage import ensure_bucket_exists, upload_file

DEMO_ORG_SLUG = "demo-org"
DEMO_WORKSPACE_SLUG = "demo-workspace"
# .local is not a valid public TLD -- the real EmailStr validator both
# /auth/signup and /auth/login use rejects it ("special-use or reserved
# name"), discovered live while actually trying to log in as this seeded
# user through the real app, not just inspecting the code. A plain
# ORM-level User(email=...) insert (this file) skips that validation
# entirely, which is exactly how this went unnoticed until now -- the
# row existed, it just could never actually be logged into.
DEMO_USER_EMAIL = "demo@example.com"
DEMO_USER_PASSWORD = "Demo12345!"
DEMO_KNOWLEDGE_BASE_SLUG = "demo-knowledge-base"
DEMO_ASSISTANT_SLUG = "demo-assistant"
DEMO_DOCUMENT_FILENAME = "agentforge-overview.md"

# Real content about this project itself, not lorem-ipsum filler --
# querying the demo assistant with "what is AgentForge" or "what can it
# do" should return an actually relevant answer once the pipeline below
# has finished processing it.
DEMO_DOCUMENT_CONTENT = """\
# AgentForge overview

AgentForge is a multi-tenant AI SaaS platform for building and deploying
AI chatbots and AI voice bots that share one intelligence layer. An
organization uploads its own documents, and AgentForge turns them into a
searchable knowledge base an AI assistant can answer questions from.

## Core capabilities

- Multi-tenant isolation: every organization's data is isolated with
  Postgres Row-Level Security, enforced again at the application layer.
- Document ingestion: uploads are virus-scanned, text-extracted, chunked
  using a strategy chosen per document, and embedded for search.
- Retrieval: hybrid vector + keyword search with reranking, so an
  assistant's answers cite the real source chunks they came from.
- Multi-agent orchestration: a LangGraph-based orchestrator coordinates
  specialized agents (retrieval, reasoning, quality review, safety) to
  produce a response.
- Memory: conversations retain context across turns and across sessions.
- Voice: the same conversation intelligence is reachable over a real
  audio call, not a separate bot -- speech-to-text in, the orchestrator
  runs, text-to-speech out, with barge-in support.
- Embeddable widget: a single script tag deploys chat and voice on any
  website, authenticated by an anonymous session token.
- Admin dashboard: organization owners configure assistants, review
  analytics, and manage members and security settings.

## Deployment

AgentForge ships as Docker images with a documented self-hosted
deployment path (docker-compose.prod.yml) and real CI/CD (GitHub
Actions building, testing, and pushing images on every change to main).
"""


async def _seed_demo_document(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
) -> uuid.UUID:
    content = DEMO_DOCUMENT_CONTENT.encode("utf-8")
    await scan_for_viruses(content)

    document_id = uuid.uuid4()
    storage_key = f"{tenant_id}/{knowledge_base_id}/{document_id}/{DEMO_DOCUMENT_FILENAME}"

    await ensure_bucket_exists()
    await upload_file(key=storage_key, content=content, content_type="text/markdown")

    repo = DocumentRepository(session, tenant_id)
    document = await repo.create(
        id=document_id,
        knowledge_base_id=knowledge_base_id,
        title=DEMO_DOCUMENT_FILENAME,
        storage_key=storage_key,
        content_type="text/markdown",
        size_bytes=len(content),
    )
    return document.id


async def seed() -> None:
    logger = get_logger(__name__)

    async with get_session() as session:
        existing = await session.execute(
            select(Organization).where(Organization.slug == DEMO_ORG_SLUG)
        )
        org = existing.scalar_one_or_none()
        if org is not None:
            logger.info("seed_skipped_org_exists", slug=DEMO_ORG_SLUG)
            return

        org = Organization(name="Demo Organization", slug=DEMO_ORG_SLUG)
        session.add(org)
        await session.flush()
        logger.info("seed_created_organization", id=str(org.id), slug=org.slug)

        user = User(
            email=DEMO_USER_EMAIL,
            full_name="Demo User",
            hashed_password=hash_password(DEMO_USER_PASSWORD),
            is_email_verified=True,
        )
        session.add(user)
        await session.flush()
        logger.info("seed_created_user", id=str(user.id), email=user.email)

        admin_role = (
            await session.execute(select(Role).where(Role.name == "org_owner"))
        ).scalar_one()

        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Demo Workspace", slug=DEMO_WORKSPACE_SLUG)
        session.add(workspace)
        await session.flush()
        logger.info("seed_created_workspace", id=str(workspace.id), slug=workspace.slug)

        membership = Membership(
            tenant_id=org.id, user_id=user.id, workspace_id=None, role_id=admin_role.id
        )
        session.add(membership)
        await session.flush()
        logger.info("seed_created_membership", user_id=str(user.id), org_id=str(org.id))

        kb_repo = KnowledgeBaseRepository(session, org.id)
        knowledge_base = await kb_repo.create(
            workspace_id=workspace.id,
            name="Demo Knowledge Base",
            slug=DEMO_KNOWLEDGE_BASE_SLUG,
            description="Documents about AgentForge itself, for trying out retrieval.",
        )
        logger.info(
            "seed_created_knowledge_base", id=str(knowledge_base.id), slug=knowledge_base.slug
        )

        document_id = await _seed_demo_document(session, org.id, knowledge_base.id)
        logger.info(
            "seed_created_document", id=str(document_id), knowledge_base_id=str(knowledge_base.id)
        )
        dispatch_extraction.delay(str(document_id), str(org.id))

        assistant_repo = AssistantRepository(session, org.id)
        assistant = await assistant_repo.create(
            knowledge_base_id=knowledge_base.id,
            name="Demo Assistant",
            slug=DEMO_ASSISTANT_SLUG,
            description="Answers questions about AgentForge using the demo knowledge base.",
            instructions=(
                "You are a helpful assistant answering questions about the AgentForge "
                "project using the documents in this knowledge base."
            ),
            agent_configuration=AgentConfiguration().model_dump(),
        )
        logger.info("seed_created_assistant", id=str(assistant.id), slug=assistant.slug)

        await session.commit()
        logger.info(
            "seed_complete",
            organization_slug=DEMO_ORG_SLUG,
            workspace_slug=DEMO_WORKSPACE_SLUG,
            user_email=DEMO_USER_EMAIL,
            knowledge_base_slug=DEMO_KNOWLEDGE_BASE_SLUG,
            assistant_slug=DEMO_ASSISTANT_SLUG,
        )
        logger.info(
            "seed_demo_document_processing_note",
            note=(
                "the demo document is queued for extraction/chunking/embedding but a "
                "Celery worker must be running to actually process it -- `make worker-dev`"
            ),
        )
        # Plain print, not structured logging -- a real, known local-dev-only
        # credential is fine to print for a human to read once at seed time,
        # but doesn't belong in the same structured log stream everything
        # else here goes through (ADR-0004's own "avoid exposing secrets in
        # logs" guidance, applied even to an intentionally-public dev value).
        print(
            f"\nLog in at http://localhost:3000/login as {DEMO_USER_EMAIL} / {DEMO_USER_PASSWORD}"
        )


def main() -> None:
    configure_logging()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
