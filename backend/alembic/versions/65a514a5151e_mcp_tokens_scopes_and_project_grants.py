"""mcp_tokens: scopes and project grants

What a person allowed an agent to do, and on which projects. Both null for
every row made before, which reads as project setup on every project: what
those agents could already do.

Revision ID: 65a514a5151e
Revises: 25605b8928a6
Create Date: 2026-11-25 19:34:53.546811
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '65a514a5151e'
down_revision = '25605b8928a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('mcp_tokens', sa.Column('scopes', sa.String(), nullable=True))
    op.add_column('mcp_tokens', sa.Column('project_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))


def downgrade() -> None:
    op.drop_column('mcp_tokens', 'project_ids')
    op.drop_column('mcp_tokens', 'scopes')

