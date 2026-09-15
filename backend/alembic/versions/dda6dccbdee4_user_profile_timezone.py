"""user profile timezone

The zone an agent resolves relative dates in. "Last week" is seven specific
days, and which seven depends on whose week it is; everything before this
column resolved to UTC, which is why the default is '' (read as UTC) rather
than a guess.

Autogenerate produced eighteen other operations alongside this one — dropping
the content video columns, ``content_plans.strategy``, the ``project_memories``
FTS index and three constraints. None of them are real: the development
database carries schema from branches whose migrations are not in this
lineage, so the model-versus-database diff reads their tables as drift. They
were removed by hand. If a future autogenerate here offers to drop something
you did not add, it is the same thing, not a discovery.

Revision ID: dda6dccbdee4
Revises: f24e9528b320
Create Date: 2026-09-14 20:51:38.030993
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'dda6dccbdee4'
down_revision = 'f24e9528b320'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_profile',
        sa.Column('timezone', sa.String(), server_default='', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('user_profile', 'timezone')
