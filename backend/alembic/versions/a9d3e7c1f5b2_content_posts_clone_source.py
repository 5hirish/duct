"""content_posts: the reference a post was cloned from

Revision ID: a9d3e7c1f5b2
Revises: b336354c84b5
Create Date: 2026-09-26 00:00:00.000000

A post cloned from a pasted TikTok (issue #222) records its source: the saved
`discovered_reference` asset, the post's URL and author, why it worked, and
the clone's FIT × PROOF call. One JSON column on the post, not a table: it is
a fact about this post, read wherever the post is, and none of the four
stores that overlap on purpose answers it — `agent_events` holds the run that
made the clone, not a link a post page can read.

Nullable, no default: every existing post was not cloned, which is what NULL
says. Written only by `submit_post_draft`, so no backfill.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'a9d3e7c1f5b2'
down_revision = 'b336354c84b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column(
            'clone_source',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'clone_source')
