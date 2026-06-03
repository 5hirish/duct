"""content agent schema: project identity + content tables

Revision ID: f6fa9305fb03
Revises: c1a96c4da25a
Create Date: 2026-05-23 00:00:00.000000
"""
from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = 'f6fa9305fb03'
down_revision = 'c1a96c4da25a'
branch_labels = None
depends_on = None


_SLUG_RE = re.compile(r'[^a-z0-9]+')


def _slugify(value: str) -> str:
    s = _SLUG_RE.sub('-', (value or '').lower()).strip('-')
    return s or 'project'


def upgrade() -> None:
    # ── projects: identity columns + content JSONB columns ──────────────────
    op.add_column('projects', sa.Column('slug', sa.String(), nullable=False, server_default=''))
    op.add_column('projects', sa.Column('tagline', sa.String(), nullable=False, server_default=''))
    op.add_column('projects', sa.Column('description', Text(), nullable=False, server_default=''))
    op.add_column('projects', sa.Column('url', sa.String(), nullable=False, server_default=''))
    op.add_column('projects', sa.Column(
        'content_brand',
        postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}',
    ))
    op.add_column('projects', sa.Column(
        'content_pillars',
        postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}',
    ))
    op.add_column('projects', sa.Column(
        'content_visual_assets',
        postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}',
    ))

    # Backfill slugs from name; ensure per-user uniqueness with a counter.
    bind = op.get_bind()
    rows = bind.execute(sa.text('SELECT id, user_id, name FROM projects')).fetchall()
    seen: dict[tuple, int] = {}
    for row in rows:
        base = _slugify(row.name or '')
        key = (row.user_id, base)
        n = seen.get(key, 0)
        slug = base if n == 0 else f"{base}-{n + 1}"
        seen[key] = n + 1
        bind.execute(
            sa.text('UPDATE projects SET slug = :slug WHERE id = :id'),
            {'slug': slug, 'id': row.id},
        )

    op.create_unique_constraint('uq_projects_user_slug', 'projects', ['user_id', 'slug'])

    # ── content_plans ───────────────────────────────────────────────────────
    op.create_table(
        'content_plans',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(), nullable=False, server_default=''),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('character', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('days', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_content_plans_project_id'), 'content_plans', ['project_id'], unique=False)

    # ── content_avatars ─────────────────────────────────────────────────────
    op.create_table(
        'content_avatars',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(), nullable=False, server_default=''),
        sa.Column('data', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_content_avatars_project_id'), 'content_avatars', ['project_id'], unique=False)

    # ── content_formats ─────────────────────────────────────────────────────
    op.create_table(
        'content_formats',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False, server_default=''),
        sa.Column('data', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'slug', name='uq_content_formats_project_slug'),
    )
    op.create_index(op.f('ix_content_formats_project_id'), 'content_formats', ['project_id'], unique=False)

    # ── content_posts ───────────────────────────────────────────────────────
    op.create_table(
        'content_posts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('plan_id', sa.Uuid(), nullable=True),
        sa.Column('day_index', sa.Integer(), nullable=True),
        sa.Column('post_dir_slug', sa.String(), nullable=False),
        sa.Column('pillar', sa.String(), nullable=False, server_default=''),
        sa.Column('topic', sa.String(), nullable=False, server_default=''),
        sa.Column('topic_id', sa.Integer(), nullable=True),
        sa.Column('post_type', sa.String(), nullable=False, server_default='slideshow'),
        sa.Column('format_style', sa.String(), nullable=False, server_default='D'),
        sa.Column('avatar_id', sa.Uuid(), nullable=True),
        sa.Column('slide_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('slides_html', Text(), nullable=False, server_default=''),
        sa.Column('caption', Text(), nullable=False, server_default=''),
        sa.Column('hashtags', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='[]'),
        sa.Column('tiktok_title', sa.String(), nullable=False, server_default=''),
        sa.Column('hook_type', sa.String(), nullable=False, server_default=''),
        sa.Column('hook_text', Text(), nullable=False, server_default=''),
        sa.Column('image_prompts', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='[]'),
        sa.Column('audio_note', Text(), nullable=False, server_default=''),
        sa.Column('platforms', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='[]'),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tiktok_url', sa.String(), nullable=False, server_default=''),
        sa.Column('post_bridge_post_id', sa.String(), nullable=False, server_default=''),
        sa.Column('post_bridge_result_id', sa.String(), nullable=False, server_default=''),
        sa.Column('perf', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('daily_perf', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='[]'),
        sa.Column('notes', Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['content_plans.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['avatar_id'], ['content_avatars.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'post_dir_slug', name='uq_content_posts_project_slug'),
    )
    op.create_index(op.f('ix_content_posts_project_id'), 'content_posts', ['project_id'], unique=False)
    op.create_index('ix_content_posts_project_status', 'content_posts', ['project_id', 'status'], unique=False)

    # ── content_assets ──────────────────────────────────────────────────────
    op.create_table(
        'content_assets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('post_id', sa.Uuid(), nullable=True),
        sa.Column('asset_type', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='upload'),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False, server_default=''),
        sa.Column('mime_type', sa.String(), nullable=False, server_default=''),
        sa.Column('prompt', Text(), nullable=False, server_default=''),
        sa.Column('model', sa.String(), nullable=False, server_default=''),
        sa.Column('params', postgresql.JSONB(astext_type=Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['post_id'], ['content_posts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_content_assets_project_id'), 'content_assets', ['project_id'], unique=False)
    op.create_index('ix_content_assets_project_type', 'content_assets', ['project_id', 'asset_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_content_assets_project_type', table_name='content_assets')
    op.drop_index(op.f('ix_content_assets_project_id'), table_name='content_assets')
    op.drop_table('content_assets')

    op.drop_index('ix_content_posts_project_status', table_name='content_posts')
    op.drop_index(op.f('ix_content_posts_project_id'), table_name='content_posts')
    op.drop_table('content_posts')

    op.drop_index(op.f('ix_content_formats_project_id'), table_name='content_formats')
    op.drop_table('content_formats')

    op.drop_index(op.f('ix_content_avatars_project_id'), table_name='content_avatars')
    op.drop_table('content_avatars')

    op.drop_index(op.f('ix_content_plans_project_id'), table_name='content_plans')
    op.drop_table('content_plans')

    op.drop_constraint('uq_projects_user_slug', 'projects', type_='unique')
    op.drop_column('projects', 'content_visual_assets')
    op.drop_column('projects', 'content_pillars')
    op.drop_column('projects', 'content_brand')
    op.drop_column('projects', 'url')
    op.drop_column('projects', 'description')
    op.drop_column('projects', 'tagline')
    op.drop_column('projects', 'slug')
