"""content_posts: scheduled_at column

Revision ID: e2a4c8f15d63
Revises: d8b3f0a16c41
Create Date: 2026-06-05 00:00:00.000000

Persist the schedule time set in the publish flow so the calendar/week view
can place a post at its scheduled date/time and badge it "scheduled".
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'e2a4c8f15d63'
down_revision = 'd8b3f0a16c41'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'scheduled_at')
