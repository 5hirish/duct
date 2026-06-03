"""content posts: hook_emotion + save_cta + bridge_text columns

Revision ID: b8d4f1a3c9e2
Revises: a3f2e8c1d4b9
Create Date: 2026-05-28 00:00:00.000000

Adds three fields per the TikTok content patterns ported from nomadapps
PR #37 (see /root/.claude/plans/just-like-our-seo-wondrous-pixel.md →
Phase 8):

  - hook_emotion — one of frustration/shock/disbelief/anger/sadness;
    the underlying emotional trigger driving slide 1. Stored as plain
    text (not enum-typed) for flexibility; the agent + Pydantic layer
    enforce the allowed set.
  - save_cta — the slide-1 parenthetical 'save this — the self-test is
    on slide 3' that names a specific payoff. Separate from hook_text
    so it stays queryable.
  - bridge_text — slide-6 personal-discovery bridge ('I found a free
    app for this. one photo. 30 seconds.'). Replaces ad-style framing.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'b8d4f1a3c9e2'
down_revision = 'a3f2e8c1d4b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('hook_emotion', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column(
        'content_posts',
        sa.Column('save_cta', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column(
        'content_posts',
        sa.Column('bridge_text', sa.Text(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'bridge_text')
    op.drop_column('content_posts', 'save_cta')
    op.drop_column('content_posts', 'hook_emotion')
