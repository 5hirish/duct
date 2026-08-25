"""add email_sent_at to lead_magnets

Revision ID: c9e2a4f1b803
Revises: b2c9f4d8e103
Create Date: 2026-06-02 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c9e2a4f1b803'
down_revision = 'f3f9ac94c4ac'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('lead_magnets',
        sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('lead_magnets', 'email_sent_at')
