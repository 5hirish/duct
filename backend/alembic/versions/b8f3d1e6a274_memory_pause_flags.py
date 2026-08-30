"""memory_paused on projects and users — the off switch for memory

Phase 2 of the memory design: memory the user controls needs a way to stop it,
per project (nothing new is remembered about this account) and per user (nothing
new is inferred about me). Reads are unaffected — pausing stops *writing*, it
does not hide what is already known; that is what archive and delete are for.

A column rather than a settings blob because every write path checks it, and a
boolean predicate the DB can answer is cheaper than parsing JSON on each call.

Revision ID: b8f3d1e6a274
Revises: a4e1c7d2b953
Create Date: 2026-08-29 10:55:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'b8f3d1e6a274'
down_revision = 'a4e1c7d2b953'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('memory_paused', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('memory_paused', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('users', 'memory_paused')
    op.drop_column('projects', 'memory_paused')
