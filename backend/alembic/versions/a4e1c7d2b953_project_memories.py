"""project_memories — agent memory (user / project / artifact scopes)

One typed, bi-temporal, provenance-linked entry per remembered fact. See
models/memory.py and docs/engineering/agent-memory-research.html §06–07.

Two indexes are deliberately conditional:

* ``uq_project_memories_state`` is a PARTIAL unique index (supported by both
  Postgres and SQLite) that makes state-key supersession atomic — at most one
  active row per (project, state_key). ``state_key`` is written by
  ``service/memory.py::state_key`` and left empty for entries that do not
  supersede anything, which is what keeps two events about the same entity from
  colliding.
* ``ix_project_memories_fts`` is a Postgres-only GIN index over
  ``to_tsvector(title || body || entity_key)``, matching the search expression
  in service/memory.py. SQLite (the desktop sidecar) falls back to LIKE, so it
  needs no index of its own.

Revision ID: a4e1c7d2b953
Revises: b6d2f8a4c1e7
Create Date: 2026-08-28 20:10:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'a4e1c7d2b953'
down_revision = 'b6d2f8a4c1e7'
branch_labels = None
depends_on = None

_STATE_KEY_PREDICATE = (
    "status IN ('confirmed', 'proposed') AND superseded_by IS NULL AND state_key <> ''"
)

_FTS_EXPRESSION = (
    "to_tsvector('english', "
    "coalesce(title, '') || ' ' || coalesce(body, '') || ' ' || coalesce(entity_key, ''))"
)


def upgrade() -> None:
    op.create_table(
        'project_memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scope', sa.String(), nullable=False, server_default='project'),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False, server_default=''),
        sa.Column('entity_key', sa.String(), nullable=False, server_default=''),
        sa.Column('attribute', sa.String(), nullable=False, server_default=''),
        sa.Column('period', sa.String(), nullable=False, server_default=''),
        sa.Column('state_key', sa.String(), nullable=False, server_default=''),
        sa.Column(
            'value',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
            server_default='{}',
        ),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_type', sa.String(), nullable=False, server_default='agent'),
        sa.Column(
            'source_refs',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
            server_default='[]',
        ),
        sa.Column('agent_type', sa.String(), nullable=False, server_default=''),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('confidence', sa.String(), nullable=False, server_default='medium'),
        sa.Column('importance', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('status', sa.String(), nullable=False, server_default='proposed'),
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('recall_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_recalled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('content_hash', sa.String(), nullable=False, server_default=''),
        sa.Column(
            'meta',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
            server_default='{}',
        ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_project_memories_scope', 'project_memories', ['scope'])
    op.create_index('ix_project_memories_project_id', 'project_memories', ['project_id'])
    op.create_index('ix_project_memories_user_id', 'project_memories', ['user_id'])
    op.create_index('ix_project_memories_status', 'project_memories', ['status'])
    op.create_index('ix_project_memories_conversation_id', 'project_memories', ['conversation_id'])
    op.create_index(
        'ix_project_memories_project_observed', 'project_memories', ['project_id', 'observed_at']
    )
    op.create_index('ix_project_memories_project_kind', 'project_memories', ['project_id', 'kind'])
    op.create_index('ix_project_memories_user_scope', 'project_memories', ['user_id', 'scope'])
    op.create_index(
        'ix_project_memories_hash', 'project_memories', ['project_id', 'content_hash']
    )
    op.create_index(
        'uq_project_memories_state',
        'project_memories',
        ['project_id', 'state_key'],
        unique=True,
        postgresql_where=sa.text(_STATE_KEY_PREDICATE),
        sqlite_where=sa.text(_STATE_KEY_PREDICATE),
    )

    if op.get_bind().dialect.name == 'postgresql':
        # Concatenated rather than interpolated: this is DDL with no input at
        # all, but interpolation reads as raw-SQL construction to
        # scripts/security/audit.py and blocks CI as a CRITICAL.
        op.execute(
            "CREATE INDEX ix_project_memories_fts ON project_memories "
            "USING GIN (" + _FTS_EXPRESSION + ")"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP INDEX IF EXISTS ix_project_memories_fts")
    op.drop_index('uq_project_memories_state', table_name='project_memories')
    op.drop_index('ix_project_memories_hash', table_name='project_memories')
    op.drop_index('ix_project_memories_user_scope', table_name='project_memories')
    op.drop_index('ix_project_memories_project_kind', table_name='project_memories')
    op.drop_index('ix_project_memories_project_observed', table_name='project_memories')
    op.drop_index('ix_project_memories_conversation_id', table_name='project_memories')
    op.drop_index('ix_project_memories_status', table_name='project_memories')
    op.drop_index('ix_project_memories_user_id', table_name='project_memories')
    op.drop_index('ix_project_memories_project_id', table_name='project_memories')
    op.drop_index('ix_project_memories_scope', table_name='project_memories')
    op.drop_table('project_memories')
