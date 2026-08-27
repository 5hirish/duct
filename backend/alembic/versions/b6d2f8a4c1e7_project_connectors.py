"""project_connectors — per-project connector→account bindings

A project can point each connector type at ONE of its members' stored
credential rows (e.g. project A bills through Stripe account X, project B
through account Y). Credentials stay deduplicated in connector_credentials;
this table only decides which account a project uses. Resolution order:
project binding → caller's user rows → env (service/execution/creds.py).

Revision ID: b6d2f8a4c1e7
Revises: e3c9d5a7b2f8
Create Date: 2026-08-27 18:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b6d2f8a4c1e7'
down_revision = 'e3c9d5a7b2f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'project_connectors',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connector_type', sa.String(), nullable=False),
        sa.Column('connector_credential_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['connector_credential_id'], ['connector_credentials.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'project_id', 'connector_type', name='uq_project_connectors_project_type'
        ),
    )
    op.create_index('ix_project_connectors_project_id', 'project_connectors', ['project_id'])
    op.create_index(
        'ix_project_connectors_connector_credential_id',
        'project_connectors',
        ['connector_credential_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_project_connectors_connector_credential_id', table_name='project_connectors'
    )
    op.drop_index('ix_project_connectors_project_id', table_name='project_connectors')
    op.drop_table('project_connectors')
