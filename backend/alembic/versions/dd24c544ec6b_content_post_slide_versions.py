"""content post slide versions

Each slide's earlier states, so the person or the agent can put one back
(agents/content/slide_versions.py). Additive: every post reads as having no
history until a slide next changes.

Revision ID: dd24c544ec6b
Revises: e9b429a0028a
Create Date: 2026-11-27 10:28:56.006936
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'dd24c544ec6b'
down_revision = 'e9b429a0028a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('content_posts', sa.Column('slide_versions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), server_default='{}', nullable=False))


def downgrade() -> None:
    op.drop_column('content_posts', 'slide_versions')

