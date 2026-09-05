"""record what a conversation's run is doing, and why it stopped

Revision ID: c3a9f1e7d2b4
Revises: e7b2c9d40a15
Create Date: 2026-09-05 00:00:00.000000

A failure used to exist only as a stream event. Reload the tab and the
transcript ended on the user's message with no reply and no reason; the desk
listed the thread as "Open" while it was in fact stuck on a rejected key. The
list route and the state route now carry `run_status` (idle / running / paused
/ failed / cancelled — `RunStatus` in agents/core/events.py) and, for the last
two, `run_error` with the same {code, retryable, error} the live client acted
on. ConversationRecorder writes both from the event stream, so every agent
reports them the same way and no runner needed a hook.

Default `idle`: every row predating this migration is a conversation nobody
is running right now, which is what idle means.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'c3a9f1e7d2b4'
down_revision = 'e7b2c9d40a15'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'agent_conversations',
        sa.Column('run_status', sa.String(), nullable=False, server_default='idle'),
    )
    op.add_column(
        'agent_conversations',
        sa.Column(
            'run_error',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('agent_conversations', 'run_error')
    op.drop_column('agent_conversations', 'run_status')
