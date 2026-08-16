"""project members + email invitations (project-level collaboration)

Revision ID: f1c7b4d92a08
Revises: e9a1c3b7d540
Create Date: 2026-08-16 00:00:00.000000

Introduces the access list a project is shared through. `projects.user_id`
stays the owner column — this migration backfills one `owner` row per existing
project from it, so every project has a complete member list from day one and
route code can query membership uniformly instead of special-casing the owner.

`project_invitations` holds pending grants addressed to an email. Only the
SHA-256 hash of the invite token is stored; the plaintext lives in the emailed
link and nowhere else.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'f1c7b4d92a08'
down_revision = 'e9a1c3b7d540'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'project_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(), server_default='collaborator', nullable=False),
        sa.Column('invited_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'user_id', name='uq_project_members_project_user'),
        sa.CheckConstraint(
            "role IN ('owner', 'collaborator')",
            name='ck_project_members_role_allowed',
        ),
    )
    op.create_index('ix_project_members_project_id', 'project_members', ['project_id'])
    op.create_index('ix_project_members_user_id', 'project_members', ['user_id'])
    op.create_index(
        'uq_project_members_single_owner', 'project_members', ['project_id'],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )

    op.create_table(
        'project_invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('role', sa.String(), server_default='collaborator', nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('invited_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['accepted_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_project_invitations_token_hash'),
        sa.CheckConstraint('email = lower(email)', name='ck_project_invitations_email_lowercase'),
        sa.CheckConstraint(
            "role IN ('owner', 'collaborator')",
            name='ck_project_invitations_role_allowed',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked')",
            name='ck_project_invitations_status_allowed',
        ),
    )
    op.create_index('ix_project_invitations_project_id', 'project_invitations', ['project_id'])
    op.create_index('ix_project_invitations_token_hash', 'project_invitations', ['token_hash'])
    op.create_index(
        'ix_project_invitations_email_status', 'project_invitations', ['email', 'status'],
    )
    op.create_index(
        'uq_project_invitations_pending_email', 'project_invitations', ['project_id', 'email'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Backfill: every existing project gets an owner row from projects.user_id.
    op.execute(
        sa.text(
            """
            INSERT INTO project_members (id, project_id, user_id, role, created_at, updated_at)
            SELECT gen_random_uuid(), p.id, p.user_id, 'owner', now(), now()
            FROM projects p
            ON CONFLICT ON CONSTRAINT uq_project_members_project_user DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index('uq_project_invitations_pending_email', table_name='project_invitations')
    op.drop_index('ix_project_invitations_email_status', table_name='project_invitations')
    op.drop_index('ix_project_invitations_token_hash', table_name='project_invitations')
    op.drop_index('ix_project_invitations_project_id', table_name='project_invitations')
    op.drop_table('project_invitations')
    op.drop_index('uq_project_members_single_owner', table_name='project_members')
    op.drop_index('ix_project_members_user_id', table_name='project_members')
    op.drop_index('ix_project_members_project_id', table_name='project_members')
    op.drop_table('project_members')
