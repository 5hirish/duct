"""versioned artifact store

Durable agent outputs (reports first; documents/tickets/images later).
group_id is the stable Claude-style artifact identity, one row per immutable
version. Content is either structured_json (template-rendered payloads) or a
private object-storage key (freehand HTML etc.) served only through the authed
/api/user/artifacts endpoints. conversation_id is a polymorphic many-to-one
link to agent_conversations (no FK) — one chat can produce many artifacts.

Revision ID: b7e2d4f8a1c3
Revises: d1f3b7a25c40
Create Date: 2026-08-26 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b7e2d4f8a1c3'
down_revision = 'd1f3b7a25c40'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_type', sa.String(), server_default='', nullable=False),
        sa.Column('kind', sa.String(), server_default='report', nullable=False),
        sa.Column('content_type', sa.String(), server_default='', nullable=False),
        sa.Column('title', sa.String(), server_default='', nullable=False),
        sa.Column('filename', sa.String(), server_default='', nullable=False),
        sa.Column('storage_key', sa.String(), server_default='', nullable=False),
        sa.Column('size_bytes', sa.Integer(), server_default='0', nullable=False),
        sa.Column('checksum', sa.String(), server_default='', nullable=False),
        sa.Column('structured_json', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('summary', sa.Text(), server_default='', nullable=False),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'version', name='uq_artifacts_group_version'),
    )
    op.create_index('ix_artifacts_group_id', 'artifacts', ['group_id'])
    op.create_index('ix_artifacts_project_id', 'artifacts', ['project_id'])
    op.create_index('ix_artifacts_conversation_id', 'artifacts', ['conversation_id'])
    op.create_index('ix_artifacts_project_created', 'artifacts', ['project_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_artifacts_project_created', table_name='artifacts')
    op.drop_index('ix_artifacts_conversation_id', table_name='artifacts')
    op.drop_index('ix_artifacts_project_id', table_name='artifacts')
    op.drop_index('ix_artifacts_group_id', table_name='artifacts')
    op.drop_table('artifacts')
