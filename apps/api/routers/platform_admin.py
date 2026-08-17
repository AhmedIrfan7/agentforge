"""Cross-org platform-admin views (roadmap step 249) -- AGENTS.md's own
PLATFORM ADMINISTRATION section names "View organizations" and "Review
aggregate metrics" among the real, buildable subset of its own broader
list. Subscriptions/abuse reports/platform-wide announcements have no
real data model anywhere in this codebase yet -- AGENTS.md's own
"FUTURE BILLING" section header already says subscriptions are
explicitly future work, and neither "abuse reports" nor "platform-wide
announcements" have a dedicated roadmap step naming them through 250;
real, undated future work, not silently folded in here.

One real endpoint covers both real capabilities: each organization's
row already carries the per-org counts a "view organizations" table
needs, and a platform-wide "aggregate metrics" view is nothing more
than summing those same real numbers -- two honest readers of one real
per-org query, not a reason to build a second backend endpoint that
would just repeat the identical per-org loop.

AGENTS.md is explicit: "Platform administrators should never
accidentally violate tenant privacy... Respect isolation wherever
possible." RLS is FORCE-enabled with no bypass (migrations/rls.py) --
there is no single cross-tenant SQL query this endpoint could even run,
even if it wanted to. Instead, this iterates every real Organization
(itself NOT tenant-scoped -- "Organization IS the tenant boundary",
models/organization.py's own docstring) and calls set_tenant_context
per org before each org's own scoped counts -- the exact same RLS the
rest of this app already relies on, applied once per tenant rather than
bypassed. Not the fastest possible query (N+1 per organization), but
this is a low-traffic admin view over what a real deployment expects to
be a moderate tenant count, and it's the only approach that respects
the isolation model at all.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import set_tenant_context
from dependencies.auth import require_platform_admin
from dependencies.db import get_db
from models.conversation import Conversation
from models.document import Document
from models.membership import Membership
from models.organization import Organization
from models.workspace import Workspace
from schemas.platform_admin import OrganizationSummaryRead, PlatformOrganizationsRead

router = APIRouter(prefix="/platform-admin", tags=["platform-admin"])

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/organizations",
    response_model=PlatformOrganizationsRead,
    dependencies=[Depends(require_platform_admin)],
)
async def list_all_organizations(session: DB) -> PlatformOrganizationsRead:
    orgs = (
        (await session.execute(select(Organization).order_by(Organization.created_at)))
        .scalars()
        .all()
    )

    summaries: list[OrganizationSummaryRead] = []
    for org in orgs:
        await set_tenant_context(session, org.id)

        workspace_count = (
            await session.scalar(
                select(func.count()).select_from(Workspace).where(Workspace.tenant_id == org.id)
            )
            or 0
        )
        member_count = (
            await session.scalar(
                select(func.count(func.distinct(Membership.user_id))).where(
                    Membership.tenant_id == org.id
                )
            )
            or 0
        )
        conversation_count = (
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.tenant_id == org.id)
            )
            or 0
        )
        document_count = (
            await session.scalar(
                select(func.count()).select_from(Document).where(Document.tenant_id == org.id)
            )
            or 0
        )

        summaries.append(
            OrganizationSummaryRead(
                id=org.id,
                name=org.name,
                slug=org.slug,
                created_at=org.created_at,
                workspace_count=workspace_count,
                member_count=member_count,
                conversation_count=conversation_count,
                document_count=document_count,
            )
        )

    return PlatformOrganizationsRead(organizations=summaries)
