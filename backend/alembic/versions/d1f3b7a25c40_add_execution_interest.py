"""add execution_interest table

Revision ID: d1f3b7a25c40
Revises: c9e2a4f1b803
Create Date: 2026-06-03 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = 'd1f3b7a25c40'
down_revision = 'c9e2a4f1b803'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'execution_interest',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('lead_magnet_id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('website_url', sa.String(), nullable=False),
        sa.Column('services', JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('finding_ids', JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lead_magnet_id'], ['lead_magnets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_execution_interest_lead_magnet_id'),
        'execution_interest', ['lead_magnet_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_execution_interest_lead_magnet_id'), table_name='execution_interest')
    op.drop_table('execution_interest')
