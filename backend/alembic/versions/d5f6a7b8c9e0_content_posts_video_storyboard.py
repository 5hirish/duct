"""content_posts: multi-beat video storyboard

Revision ID: d5f6a7b8c9e0
Revises: c4e5f6a7b8d9
Create Date: 2026-06-23 00:00:00.000000

Adds ``video_storyboard`` (JSONB, ordered list of beats) used when
post_type == "video". Each beat carries its keyframe prompt + (once generated)
keyframe asset id/url, mirroring slides[] — the keyframe images themselves are
ordinary content_assets rows in the same projects/{id}/generated/ bucket path.
This complements the single source_image_asset_id (added in c4e5f6a7b8d9) with a
per-shot storyboard, since image-to-video models take one clean frame per clip
(or first+last per transformation). Additive + defaulted ('[]') — existing
slideshow and single-clip video posts are untouched.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'd5f6a7b8c9e0'
down_revision = 'c4e5f6a7b8d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column(
            'video_storyboard',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'video_storyboard')
