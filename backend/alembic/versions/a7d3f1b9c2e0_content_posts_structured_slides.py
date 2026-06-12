"""content_posts: structured slides + layout (and merge content/lead-magnet heads)

Revision ID: a7d3f1b9c2e0
Revises: b3d8c1f2a640, d52f7b1ea4c8, b2c9f4d8e103
Create Date: 2026-06-08 00:00:00.000000

Two things in one revision:

1. Converge the three divergent heads that had accumulated on this branch
   (two parallel content_posts chains + the lead-magnet chain) back to a
   single head, so `alembic upgrade head` resolves again.

2. Add the structured-slides columns that back the new drafting model:
     - layout  — overall layout family (full-bleed | text-only | collage |
       before-after | editorial); denormalised from the format so render is
       self-contained.
     - slides  — JSONB list of structured slide objects (copy + image prompt +,
       once generated, image_url / image_prompt_used for staleness). This is
       the SOURCE OF TRUTH; slides_html is rendered deterministically from it.

Additive + nullable=False with server defaults, so existing rows backfill to
'full-bleed' / [] and nothing breaks.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Merge revision: a tuple down_revision unifies the three current heads.
revision = 'a7d3f1b9c2e0'
down_revision = ('b3d8c1f2a640', 'd52f7b1ea4c8', 'b2c9f4d8e103')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('layout', sa.String(), nullable=False, server_default='full-bleed'),
    )
    op.add_column(
        'content_posts',
        sa.Column(
            'slides',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'slides')
    op.drop_column('content_posts', 'layout')
