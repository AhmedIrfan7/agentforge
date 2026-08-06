"""Local dev seed script — demo org/workspace/user, for a fresh clone to
have something to look at immediately. Idempotent: safe to run repeatedly,
skips anything that already exists rather than erroring.

Usage: uv run python -m scripts.seed  (from apps/api)
"""

import asyncio

from sqlalchemy import select

from db import get_session, set_tenant_context
from logging_config import configure_logging, get_logger
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.user import User
from models.workspace import Workspace

DEMO_ORG_SLUG = "demo-org"
DEMO_WORKSPACE_SLUG = "demo-workspace"
DEMO_USER_EMAIL = "demo@agentforge.local"


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

        user = User(email=DEMO_USER_EMAIL, full_name="Demo User")
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

        await session.commit()
        logger.info(
            "seed_complete",
            organization_slug=DEMO_ORG_SLUG,
            workspace_slug=DEMO_WORKSPACE_SLUG,
            user_email=DEMO_USER_EMAIL,
        )


def main() -> None:
    configure_logging()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
