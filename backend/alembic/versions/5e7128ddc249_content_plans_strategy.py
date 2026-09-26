"""content_plans.strategy — what a plan chose from the account's history

A plan now reads the account's own posting history before it is written (#224)
and records the strategy it chose: the post type it scales, the one it tests,
the evidence for both, what past bets taught it and when to post. The app shows
it above the plan. `{}` for every plan made before this existed, which the app
reads as "no strategy recorded".

Additive, and SQLite-safe for the desktop sidecar (db/migrate.py): the JSON
variant rather than raw JSONB, and a server default so existing rows satisfy
NOT NULL.

Revision ID: 5e7128ddc249
Revises: b336354c84b5
Create Date: 2026-09-25 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '5e7128ddc249'
down_revision = 'b336354c84b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_plans',
        sa.Column(
            'strategy',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            server_default='{}',
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('content_plans', 'strategy')
