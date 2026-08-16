"""add branding fields to organizations

Revision ID: 1013c4f08ccd
Revises: 7aaec26c0dd2
Create Date: 2026-08-16 19:24:32.558258

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1013c4f08ccd"
down_revision: str | Sequence[str] | None = "7aaec26c0dd2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Both nullable, no server_default needed -- NULL is itself the real
    # "no branding set yet" value, unlike step 065's is_email_verified,
    # which needed a real backfill default for existing rows.
    op.add_column("organizations", sa.Column("logo_url", sa.String(), nullable=True))
    op.add_column("organizations", sa.Column("primary_color", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("organizations", "primary_color")
    op.drop_column("organizations", "logo_url")
