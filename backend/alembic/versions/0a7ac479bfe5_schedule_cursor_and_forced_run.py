"""agent schedules: on-release triggers (issue #563)

``cursor`` is the release tag an on-release schedule last saw; ``forced`` is
"Run now" on an event cadence, which runs once without the check.

Revision ID: 0a7ac479bfe5
Revises: 12d788dc1f73
Create Date: 2026-11-11 22:55:16.496141
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a7ac479bfe5'
down_revision = '12d788dc1f73'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agent_schedules', sa.Column('cursor', sa.String(), server_default='', nullable=False))
    op.add_column('agent_schedules', sa.Column('forced', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('agent_schedules', 'forced')
    op.drop_column('agent_schedules', 'cursor')

