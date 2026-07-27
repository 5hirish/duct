"""content_posts: drop format_style (posts now link via format_id only)

Revision ID: b3d8c1f2a640
Revises: e2a4c8f15d63
Create Date: 2026-06-05 00:00:00.000000

format_style was the legacy free-text selector ("D"). Now that posts carry a
real format_id FK (a1f3c7e9d520), the letter is redundant: posts link to a
format only by format_id, resolved from the format's slug at draft time.

Downgrade re-adds the column with the old default and best-effort backfills it
from the linked format's data.format_style.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'b3d8c1f2a640'
down_revision = 'e2a4c8f15d63'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('content_posts', 'format_style')


def downgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('format_style', sa.String(), nullable=False, server_default='D'),
    )
    op.execute(
        """
        UPDATE content_posts AS p
        SET format_style = COALESCE(NULLIF(f.data->>'format_style', ''), 'D')
        FROM content_formats AS f
        WHERE p.format_id = f.id
        """
    )
