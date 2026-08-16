"""add instructions to assistants

Revision ID: f66418ba49dc
Revises: 1013c4f08ccd
Create Date: 2026-08-16 21:21:41.073300

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f66418ba49dc"
down_revision: str | Sequence[str] | None = "1013c4f08ccd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, no server_default needed -- NULL is itself the honest
    # "no system prompt configured yet" value, same reasoning step 234's
    # own branding fields used for Organization.logo_url/primary_color.
    # sa.String() (unbounded, functionally identical to TEXT in
    # Postgres), matching Assistant.description's own column type
    # exactly rather than introducing a second string-column convention.
    op.add_column("assistants", sa.Column("instructions", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assistants", "instructions")
