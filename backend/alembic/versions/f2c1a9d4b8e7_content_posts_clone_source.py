"""content_posts: clone_source column

Revision ID: f2c1a9d4b8e7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-19 00:00:00.000000

Clone/reference lineage for posts added via the board's Add-post flow. Holds the
source pointer (manual | url | reference) plus a cache of the expensive Apify
ingest (scraped_post, media, diagnostic) so re-drafting a pending clone never
re-charges. Nullable JSONB — NULL for ordinary planner/manual posts.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'f2c1a9d4b8e7'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('clone_source', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'clone_source')
