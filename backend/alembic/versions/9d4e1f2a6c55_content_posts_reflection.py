"""content posts remember the reflection section they came from

content_posts.reflection: {"group_id", "section_id", "date"} for a post a
Daily Reflection derived (issue #270), null for every other post. The drafts
queue lists a day's drafts by it, and revising a reflection re-derives each
section's drafts in place by it instead of adding new ones.

Hand-written: one nullable JSON column, the same type as clone_source and
video. CI's `alembic check` compares it with the model.

Revision ID: 9d4e1f2a6c55
Revises: 7c1d2e9a4b30
Create Date: 2026-10-01 01:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '9d4e1f2a6c55'
down_revision = '7c1d2e9a4b30'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('reflection', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table('content_posts') as batch:
        batch.drop_column('reflection')
