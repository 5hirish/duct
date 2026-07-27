"""content_posts: drop day_index (monthly model)

Revision ID: d8b3f0a16c41
Revises: a1f3c7e9d520
Create Date: 2026-06-05 00:00:00.000000

The content plan moved from an abstract 30-day "Day N" model to a calendar
month: posts link to plan days by post_id and the calendar lays items on
sequential dates from the 1st. The positional day_index is no longer used.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'd8b3f0a16c41'
down_revision = 'a1f3c7e9d520'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('content_posts', 'day_index')


def downgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('day_index', sa.Integer(), nullable=True),
    )
