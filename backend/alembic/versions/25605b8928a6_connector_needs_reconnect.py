"""connector_credentials.needs_reconnect_at: the provider refused this sign-in

Revision ID: 25605b8928a6
Revises: 0a7ac479bfe5
Create Date: 2026-11-24 21:59:55.654686
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '25605b8928a6'
down_revision = '0a7ac479bfe5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('connector_credentials', sa.Column('needs_reconnect_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('connector_credentials', 'needs_reconnect_at')

