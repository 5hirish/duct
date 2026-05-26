"""content posts: strategic_note column

Revision ID: a3f2e8c1d4b9
Revises: f6fa9305fb03
Create Date: 2026-05-27 00:00:00.000000

The agent emits a 1-2 sentence "why this works" strategic_note alongside
each PostDraft. It explains the post's role in the broader content
strategy (pillar reinforcement, audience targeting, hook variation
intent). Surfaced in the frontend under a collapsed "Why this works"
expand.

Separate from the existing user-facing `notes` column so the agent's
reasoning doesn't collide with user notes when we add that UI.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'a3f2e8c1d4b9'
down_revision = 'f6fa9305fb03'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('strategic_note', sa.Text(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'strategic_note')
