"""staged execution: change sets + per-account guardrails

Revision ID: a7d2e5f8c941
Revises: e9a1c3b7d540
Create Date: 2026-07-31 00:00:00.000000

Two-phase-commit execution layer (propose → preview/guardrail-check →
approve → apply → verify/rollback). execution_change_sets holds the staged
changes as a JSONB list with per-change status/result/rollback handles;
execution_guardrails holds per-account learned invariants enforced at
preview and apply time. See docs/strategy/gads-learnings-ads-intelligence.md §5.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'a7d2e5f8c941'
down_revision = 'e9a1c3b7d540'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'execution_change_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connector_type', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), server_default='', nullable=False),
        sa.Column('account_name', sa.String(), server_default='', nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('context', sa.Text(), server_default='', nullable=False),
        sa.Column('status', sa.String(), server_default='proposed', nullable=False),
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_execution_change_sets_user_id', 'execution_change_sets', ['user_id'])

    op.create_table(
        'execution_guardrails',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connector_type', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), server_default='', nullable=False),
        sa.Column('rule', sa.Text(), nullable=False),
        sa.Column('match', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_execution_guardrails_user_id', 'execution_guardrails', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_execution_guardrails_user_id', table_name='execution_guardrails')
    op.drop_table('execution_guardrails')
    op.drop_index('ix_execution_change_sets_user_id', table_name='execution_change_sets')
    op.drop_table('execution_change_sets')
