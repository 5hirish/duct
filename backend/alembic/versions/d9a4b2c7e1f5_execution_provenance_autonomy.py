"""execution provenance + tiered autonomy

Agent-proposed execution (Phase 4): change sets record which
project/conversation/agent proposed them (`source`), who applied them
(`applied_by`: '' | 'user' | 'auto'), and whether the whole set was policy-
eligible for auto-apply. Projects gain `autonomy_level` ('manual' default |
'assisted') — the human-controlled dial that lets reversible, guardrail-clean,
non-destructive agent sets apply without an approval click.

Revision ID: d9a4b2c7e1f5
Revises: c8f3a1d92b4e
Create Date: 2026-08-26 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'd9a4b2c7e1f5'
down_revision = 'c8f3a1d92b4e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'execution_change_sets',
        sa.Column(
            'project_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('projects.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.add_column(
        'execution_change_sets',
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        'execution_change_sets',
        sa.Column('agent_type', sa.String(), server_default='', nullable=False),
    )
    op.add_column(
        'execution_change_sets',
        sa.Column('source', sa.String(), server_default='user', nullable=False),
    )
    op.add_column(
        'execution_change_sets',
        sa.Column('applied_by', sa.String(), server_default='', nullable=False),
    )
    op.add_column(
        'execution_change_sets',
        sa.Column('auto_apply_eligible', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index('ix_execution_change_sets_project_id', 'execution_change_sets', ['project_id'])
    op.create_index(
        'ix_execution_change_sets_conversation_id', 'execution_change_sets', ['conversation_id']
    )

    op.add_column(
        'projects',
        sa.Column('autonomy_level', sa.String(), server_default='manual', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('projects', 'autonomy_level')

    op.drop_index('ix_execution_change_sets_conversation_id', table_name='execution_change_sets')
    op.drop_index('ix_execution_change_sets_project_id', table_name='execution_change_sets')
    op.drop_column('execution_change_sets', 'auto_apply_eligible')
    op.drop_column('execution_change_sets', 'applied_by')
    op.drop_column('execution_change_sets', 'source')
    op.drop_column('execution_change_sets', 'agent_type')
    op.drop_column('execution_change_sets', 'conversation_id')
    op.drop_column('execution_change_sets', 'project_id')
