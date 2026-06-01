"""business domain schema: projects, agent_contexts, connector_credentials

Revision ID: c1a96c4da25a
Revises: 0f5f38d4084c
Create Date: 2026-05-15 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = 'c1a96c4da25a'
down_revision = '0f5f38d4084c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'projects',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('company_name', sa.String(), nullable=False, server_default=''),
        sa.Column('industry', sa.String(), nullable=False, server_default=''),
        sa.Column('targets', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('audience', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('competition', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('brand_channels', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_projects_user_id'), 'projects', ['user_id'], unique=False)

    op.create_table(
        'agent_contexts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'agent_id', name='uq_agent_contexts_project_agent'),
    )
    op.create_index(op.f('ix_agent_contexts_project_id'), 'agent_contexts', ['project_id'], unique=False)
    op.create_index(
        'ix_agent_contexts_data_gin', 'agent_contexts', ['data'],
        unique=False, postgresql_using='gin',
    )

    op.create_table(
        'connector_credentials',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('connector_type', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False, server_default=''),
        sa.Column('account_name', sa.String(), nullable=False, server_default=''),
        sa.Column('credentials_enc', sa.String(), nullable=False),
        sa.Column('last_validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'connector_type', 'account_id',
            name='uq_connector_credentials_user_type_account',
        ),
    )
    op.create_index(op.f('ix_connector_credentials_user_id'), 'connector_credentials', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_connector_credentials_user_id'), table_name='connector_credentials')
    op.drop_table('connector_credentials')

    op.drop_index('ix_agent_contexts_data_gin', table_name='agent_contexts')
    op.drop_index(op.f('ix_agent_contexts_project_id'), table_name='agent_contexts')
    op.drop_table('agent_contexts')

    op.drop_index(op.f('ix_projects_user_id'), table_name='projects')
    op.drop_table('projects')
