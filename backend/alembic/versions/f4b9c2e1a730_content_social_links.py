"""content_social_links table

Revision ID: f4b9c2e1a730
Revises: e7c4a1b9f250
Create Date: 2026-06-04 00:00:00.000000

Per-project linked social accounts. Each row links a PostBridge social account
(external_account_id) to a project, so analytics and scheduling can work off a
stable selection instead of re-listing every PostBridge account each time.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'f4b9c2e1a730'
down_revision = 'e7c4a1b9f250'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'content_social_links',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('external_account_id', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False, server_default=''),
        sa.Column('username', sa.String(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'project_id', 'external_account_id',
            name='uq_content_social_links_project_account',
        ),
    )
    op.create_index(
        op.f('ix_content_social_links_project_id'),
        'content_social_links', ['project_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_content_social_links_project_id'), table_name='content_social_links')
    op.drop_table('content_social_links')
