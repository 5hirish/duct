"""content_posts: published_via provenance column

Revision ID: c5e1a7d9b220
Revises: f4b9c2e1a730
Create Date: 2026-06-05 00:00:00.000000

Marks how a post reached the account: "duct" when it went out through our
system (the Duct publish flow or a migrated MaxAura plan), "" / "external"
when it appeared from elsewhere (TikTok Studio, PostBridge dashboard). Used to
badge analytics rows and tie PostBridge results back to local posts.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c5e1a7d9b220'
down_revision = 'f4b9c2e1a730'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('published_via', sa.String(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'published_via')
