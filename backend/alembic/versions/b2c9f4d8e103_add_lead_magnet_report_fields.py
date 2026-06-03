"""add report_json and report_generated_at to lead_magnets

Revision ID: b2c9f4d8e103
Revises: a3f8e1c7d902
Create Date: 2026-05-31 01:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b2c9f4d8e103'
down_revision = 'a3f8e1c7d902'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('lead_magnets',
        sa.Column('report_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('lead_magnets',
        sa.Column('report_generated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_lead_magnets_report_generated_at', 'lead_magnets',
                    ['report_generated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_lead_magnets_report_generated_at', table_name='lead_magnets')
    op.drop_column('lead_magnets', 'report_generated_at')
    op.drop_column('lead_magnets', 'report_json')
