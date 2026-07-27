"""content_posts: format_id FK → content_formats

Revision ID: a1f3c7e9d520
Revises: c5e1a7d9b220
Create Date: 2026-06-05 00:00:00.000000

Adds a real relationship from a post to the format it was built with. Until
now a post only carried a free-text `format_style` ("D"); the format library
lives in `content_formats` keyed by slug with `data.format_style`. This wires
them together so the UI can show the actual format name and we can navigate
post → format.

The data backfill links every existing post to a format in the same project
whose `data.format_style` matches the post's `format_style` (case-insensitive),
falling back to a `format-<style>` slug match. Posts whose project has no
matching format row keep `format_id` NULL and the UI falls back to the raw
`format_style` letter.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'a1f3c7e9d520'
down_revision = 'c5e1a7d9b220'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('content_posts', sa.Column('format_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_content_posts_format_id',
        'content_posts', 'content_formats',
        ['format_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_content_posts_format_id', 'content_posts', ['format_id'])

    # Backfill: link posts to a same-project format by format_style, then slug.
    op.execute(
        """
        UPDATE content_posts AS p
        SET format_id = f.id
        FROM content_formats AS f
        WHERE p.format_id IS NULL
          AND f.project_id = p.project_id
          AND (
                lower(f.data->>'format_style') = lower(p.format_style)
             OR f.slug = 'format-' || lower(p.format_style)
          )
        """
    )


def downgrade() -> None:
    op.drop_index('ix_content_posts_format_id', table_name='content_posts')
    op.drop_constraint('fk_content_posts_format_id', 'content_posts', type_='foreignkey')
    op.drop_column('content_posts', 'format_id')
