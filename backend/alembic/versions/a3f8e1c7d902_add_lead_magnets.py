"""add lead_magnets table

Revision ID: a3f8e1c7d902
Revises: c1a96c4da25a
Create Date: 2026-05-31 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'a3f8e1c7d902'
down_revision = 'c1a96c4da25a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'lead_magnets',
        sa.Column('id', sa.Uuid(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('website_url', sa.String(), nullable=False),
        sa.Column('magnet_type', sa.String(), nullable=False, server_default='seo_audit'),
        sa.Column('access_token', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('access_token'),
    )
    op.create_index('ix_lead_magnets_access_token', 'lead_magnets', ['access_token'], unique=True)
    op.create_index('ix_lead_magnets_email', 'lead_magnets', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_lead_magnets_email', table_name='lead_magnets')
    op.drop_index('ix_lead_magnets_access_token', table_name='lead_magnets')
    op.drop_table('lead_magnets')
