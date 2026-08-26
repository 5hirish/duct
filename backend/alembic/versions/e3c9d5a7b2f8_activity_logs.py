"""activity_logs — the project audit trail

One append-only row per lifecycle transition (change set proposed/approved/
applied/rolled back, artifact created/versioned, GTM published) with actor
attribution (user | agent | auto). Complements — never mirrors — the raw
tool-call forensics in agent_events and the terminal state on
execution_change_sets/artifacts.

Revision ID: e3c9d5a7b2f8
Revises: d9a4b2c7e1f5
Create Date: 2026-08-27 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'e3c9d5a7b2f8'
down_revision = 'd9a4b2c7e1f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'activity_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_type', sa.String(), server_default='', nullable=False),
        sa.Column('source', sa.String(), server_default='user', nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('connector_type', sa.String(), server_default='', nullable=False),
        sa.Column('account_id', sa.String(), server_default='', nullable=False),
        sa.Column('target_type', sa.String(), server_default='', nullable=False),
        sa.Column('target_id', sa.String(), server_default='', nullable=False),
        sa.Column('summary', sa.Text(), server_default='', nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_activity_logs_project_id', 'activity_logs', ['project_id'])
    op.create_index('ix_activity_logs_conversation_id', 'activity_logs', ['conversation_id'])
    op.create_index('ix_activity_logs_created_at', 'activity_logs', ['created_at'])
    op.create_index('ix_activity_logs_project_created', 'activity_logs', ['project_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_activity_logs_project_created', table_name='activity_logs')
    op.drop_index('ix_activity_logs_created_at', table_name='activity_logs')
    op.drop_index('ix_activity_logs_conversation_id', table_name='activity_logs')
    op.drop_index('ix_activity_logs_project_id', table_name='activity_logs')
    op.drop_table('activity_logs')
