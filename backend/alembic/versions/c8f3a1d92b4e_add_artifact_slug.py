"""artifact slug — model-chosen semantic identity

Kebab-case slug the agent coins at creation (Claude-artifact convention);
shared by every version of a group, unique per project among groups
(app-enforced — version rows repeat it, so no DB unique constraint).

Revision ID: c8f3a1d92b4e
Revises: b7e2d4f8a1c3
Create Date: 2026-08-26 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c8f3a1d92b4e'
down_revision = 'b7e2d4f8a1c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('artifacts', sa.Column('slug', sa.String(), server_default='', nullable=False))
    op.create_index('ix_artifacts_slug', 'artifacts', ['slug'])
    op.create_index('ix_artifacts_project_slug', 'artifacts', ['project_id', 'slug'])


def downgrade() -> None:
    op.drop_index('ix_artifacts_project_slug', table_name='artifacts')
    op.drop_index('ix_artifacts_slug', table_name='artifacts')
    op.drop_column('artifacts', 'slug')
