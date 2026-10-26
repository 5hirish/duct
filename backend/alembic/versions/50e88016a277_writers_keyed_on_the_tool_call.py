"""writers keyed on the tool call

Revision ID: 50e88016a277
Revises: c35d538b8dc9
Create Date: 2026-10-26 01:10:00.000000

A run cut between a writer tool's commit and its superstep checkpoint is
continued from the checkpoint, which executes the same tool call again.
``execution_change_sets`` and ``artifacts`` now carry the tool call that wrote
them, with one row allowed per conversation and call, so the second execution
reads the row instead of writing a twin (agents/core/tool_calls.py). Two
columns with a server default and two partial unique indexes that every
existing row (empty id) falls outside of, so it is safe to apply before the
code that writes the column deploys. The predicate is spelled for both
dialects: the desktop sidecar runs this chain on SQLite, where a plain unique
index would make two browser-made rows in one conversation collide.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '50e88016a277'
down_revision = 'c35d538b8dc9'
branch_labels = None
depends_on = None

_PRESENT = "tool_call_id <> ''"


def upgrade() -> None:
    op.add_column(
        'execution_change_sets',
        sa.Column('tool_call_id', sa.String(), server_default='', nullable=False),
    )
    op.create_index(
        'uq_execution_change_sets_tool_call',
        'execution_change_sets',
        ['conversation_id', 'tool_call_id'],
        unique=True,
        postgresql_where=sa.text(_PRESENT),
        sqlite_where=sa.text(_PRESENT),
    )
    op.add_column(
        'artifacts',
        sa.Column('tool_call_id', sa.String(), server_default='', nullable=False),
    )
    op.create_index(
        'uq_artifacts_tool_call',
        'artifacts',
        ['conversation_id', 'tool_call_id'],
        unique=True,
        postgresql_where=sa.text(_PRESENT),
        sqlite_where=sa.text(_PRESENT),
    )


def downgrade() -> None:
    op.drop_index('uq_artifacts_tool_call', table_name='artifacts')
    op.drop_column('artifacts', 'tool_call_id')
    op.drop_index('uq_execution_change_sets_tool_call', table_name='execution_change_sets')
    op.drop_column('execution_change_sets', 'tool_call_id')
