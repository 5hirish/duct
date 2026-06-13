"""agent conversations + events (session persistence / resume)

Revision ID: e9a1c3b7d540
Revises: d2f7a4c1e9b3
Create Date: 2026-06-13 00:00:00.000000

Persists agent chat history + resume state so a session can be rebuilt on
reopen (the artifact — post/plan — already lives in content_posts /
content_plans). agent_conversations links to an artifact polymorphically
(artifact_type + artifact_id, no FK) so it scales to any agent type;
agent_events is a generic append-only log (free-string `kind`, JSONB `data`).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'e9a1c3b7d540'
down_revision = 'd2f7a4c1e9b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_type', sa.String(), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('mode', sa.String(), server_default='draft_post', nullable=False),
        sa.Column('artifact_type', sa.String(), nullable=True),
        sa.Column('artifact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(), server_default='', nullable=False),
        sa.Column('status', sa.String(), server_default='active', nullable=False),
        sa.Column('summary', sa.Text(), server_default='', nullable=False),
        sa.Column('summary_through_seq', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_seq', sa.Integer(), server_default='0', nullable=False),
        sa.Column('input_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('output_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_conversations_project_id', 'agent_conversations', ['project_id'])
    op.create_index('ix_agent_conv_project_status', 'agent_conversations', ['project_id', 'status'])
    op.create_index(
        'ix_agent_conv_artifact', 'agent_conversations',
        ['agent_type', 'artifact_type', 'artifact_id'],
    )
    op.create_index(
        'uq_agent_conv_active_artifact', 'agent_conversations',
        ['artifact_type', 'artifact_id'],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND artifact_id IS NOT NULL"),
    )

    op.create_table(
        'agent_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['agent_conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'seq', name='uq_agent_events_conv_seq'),
    )
    op.create_index('ix_agent_events_conversation_id', 'agent_events', ['conversation_id'])
    op.create_index('ix_agent_events_conv_seq', 'agent_events', ['conversation_id', 'seq'])


def downgrade() -> None:
    op.drop_index('ix_agent_events_conv_seq', table_name='agent_events')
    op.drop_index('ix_agent_events_conversation_id', table_name='agent_events')
    op.drop_table('agent_events')
    op.drop_index('uq_agent_conv_active_artifact', table_name='agent_conversations')
    op.drop_index('ix_agent_conv_artifact', table_name='agent_conversations')
    op.drop_index('ix_agent_conv_project_status', table_name='agent_conversations')
    op.drop_index('ix_agent_conversations_project_id', table_name='agent_conversations')
    op.drop_table('agent_conversations')
