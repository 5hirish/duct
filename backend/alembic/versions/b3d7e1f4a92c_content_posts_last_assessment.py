"""content_posts: last_assessment column

Revision ID: b3d7e1f4a92c
Revises: e9a1c3b7d540
Create Date: 2026-06-17 00:00:00.000000

Persist the latest pre-publish review (PublishAssessment) on the post so the
review panel survives a reload and the read-only detail page can show the last
score. Nullable JSONB — NULL until a review has run.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b3d7e1f4a92c'
down_revision = 'e9a1c3b7d540'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('last_assessment', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'last_assessment')
