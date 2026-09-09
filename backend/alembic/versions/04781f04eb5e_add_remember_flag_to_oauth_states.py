"""add remember flag to oauth_states

Revision ID: 04781f04eb5e
Revises: 3867abd7b3e4
Create Date: 2026-09-09 14:02:55.049688
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '04781f04eb5e'
down_revision = '3867abd7b3e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Autogenerate also picked up unrelated drift already present on staging
    # (dropped content_posts/content_plans video+strategy columns, stale
    # indexes) — left untouched here since it predates this change and
    # dropping those columns would delete real data. Only the one column this
    # revision is actually for:
    op.add_column(
        'oauth_states',
        sa.Column('remember', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('oauth_states', 'remember')
