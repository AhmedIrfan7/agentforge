import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from db import get_session, set_tenant_context
from models.membership import Membership
from models.organization import Organization
from models.role import Role
from models.user import User
from models.workspace import Workspace


@pytest.mark.anyio
async def test_builtin_roles_are_seeded() -> None:
    async with get_session() as session:
        result = await session.execute(select(Role.name))
        names = {row[0] for row in result.all()}
        assert names == {
            "org_owner",
            "admin",
            "manager",
            "knowledge_manager",
            "developer",
            "support_agent",
            "analyst",
            "viewer",
            "end_user",
            "guest",
        }


@pytest.mark.anyio
async def test_org_level_and_workspace_level_membership_can_coexist() -> None:
    async with get_session() as session:
        org = Organization(name="Membership Test Org", slug="membership-test-org")
        user = User(email="member@example.com", full_name="Test Member")
        session.add_all([org, user])
        await session.flush()

        await set_tenant_context(session, org.id)

        workspace = Workspace(tenant_id=org.id, name="Eng", slug="eng")
        session.add(workspace)
        await session.flush()

        viewer_role = (
            await session.execute(select(Role).where(Role.name == "viewer"))
        ).scalar_one()
        admin_role = (await session.execute(select(Role).where(Role.name == "admin"))).scalar_one()

        # Same user, same org: one org-level membership (workspace_id=None)
        # plus one workspace-specific membership — both allowed.
        session.add(
            Membership(tenant_id=org.id, user_id=user.id, workspace_id=None, role_id=viewer_role.id)
        )
        session.add(
            Membership(
                tenant_id=org.id, user_id=user.id, workspace_id=workspace.id, role_id=admin_role.id
            )
        )
        await session.flush()

        result = await session.execute(select(Membership).where(Membership.user_id == user.id))
        assert len(result.all()) == 2


@pytest.mark.anyio
async def test_duplicate_org_level_membership_is_rejected() -> None:
    async with get_session() as session:
        org = Organization(name="Dup Test Org", slug="dup-membership-test-org")
        user = User(email="dupmember@example.com", full_name="Dup Member")
        session.add_all([org, user])
        await session.flush()

        viewer_role = (
            await session.execute(select(Role).where(Role.name == "viewer"))
        ).scalar_one()

        await set_tenant_context(session, org.id)
        session.add(
            Membership(tenant_id=org.id, user_id=user.id, workspace_id=None, role_id=viewer_role.id)
        )
        await session.flush()

        session.add(
            Membership(tenant_id=org.id, user_id=user.id, workspace_id=None, role_id=viewer_role.id)
        )
        with pytest.raises(DBAPIError, match="uq_memberships_org_level"):
            await session.flush()
