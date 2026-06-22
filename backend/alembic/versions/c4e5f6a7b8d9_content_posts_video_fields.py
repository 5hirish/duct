"""content_posts: single-clip video fields

Revision ID: c4e5f6a7b8d9
Revises: f2c1a9d4b8e7
Create Date: 2026-06-22 00:00:00.000000

Adds the denormalised single-clip video columns used when post_type == "video".
The clip is generated via Higgsfield (service/higgsfield), stored as a
content_assets row, and these columns point the post at the chosen clip + its
generation inputs so render + publish stay self-contained (slides[] is empty for
video posts). All additive + nullable / defaulted — existing slideshow posts are
untouched. content_assets needs no change: its mime_type/source/asset_type are
unconstrained strings ("video/mp4", "higgsfield", "generated").
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c4e5f6a7b8d9'
down_revision = 'f2c1a9d4b8e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('content_posts', sa.Column('video_url', sa.String(), nullable=False, server_default=''))
    op.add_column('content_posts', sa.Column('video_asset_id', sa.Uuid(), nullable=True))
    op.add_column('content_posts', sa.Column('video_prompt', sa.Text(), nullable=False, server_default=''))
    op.add_column('content_posts', sa.Column('video_duration_seconds', sa.Integer(), nullable=True))
    op.add_column('content_posts', sa.Column('video_aspect_ratio', sa.String(), nullable=False, server_default='9:16'))
    op.add_column('content_posts', sa.Column('source_image_asset_id', sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column('content_posts', 'source_image_asset_id')
    op.drop_column('content_posts', 'video_aspect_ratio')
    op.drop_column('content_posts', 'video_duration_seconds')
    op.drop_column('content_posts', 'video_prompt')
    op.drop_column('content_posts', 'video_asset_id')
    op.drop_column('content_posts', 'video_url')
