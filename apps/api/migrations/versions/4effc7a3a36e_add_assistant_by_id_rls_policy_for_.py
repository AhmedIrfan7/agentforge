"""add assistant by id RLS policy for anonymous lookup

Revision ID: 4effc7a3a36e
Revises: b103046e3fef
Create Date: 2026-08-15 21:51:50.230292

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4effc7a3a36e"
down_revision: str | Sequence[str] | None = "b103046e3fef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Same dual-policy idea as 0a09d64b88b6's own invitation_by_token,
    applied to an anonymous chat visitor (step 192): the public
    conversation-create endpoint only has an assistant_id, not a
    tenant_id -- tenant_isolation alone can never surface the row. A
    second, separate PERMISSIVE policy (combined with tenant_isolation
    via OR) permits SELECT where id matches the session variable set by
    db.py:set_lookup_assistant_id() -- scoped to exactly the one row
    the caller already named by ID, not a blanket bypass. The caller's
    own repositories/assistant.py:get_public_assistant_by_id() still
    checks is_public=True in the application layer on top of this --
    the RLS policy alone would let an anonymous caller SELECT any
    assistant by ID, public or not; is_public is the real authorization
    decision, this policy only makes the row visible enough to check it.
    """
    op.execute("""
        CREATE POLICY assistant_by_id ON assistants
        FOR SELECT
        USING (id = NULLIF(current_setting('app.lookup_assistant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS assistant_by_id ON assistants")
