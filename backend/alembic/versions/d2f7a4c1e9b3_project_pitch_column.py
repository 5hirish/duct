"""projects: pitch column

Revision ID: d2f7a4c1e9b3
Revises: a7d3f1b9c2e0
Create Date: 2026-06-11 00:00:00.000000

The onboarding "About your business" step captures a one-line elevator pitch
(e.g. "A meal-planning app for busy families") alongside name, industry and
business_model. It is owned by project context (the /api/user/projects editor),
kept distinct from the content agent's `tagline`/`description` so the two
editors never clobber each other's column. This adds its home on the persisted
`projects` table so it round-trips through /api/user/projects.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'd2f7a4c1e9b3'
down_revision = 'a7d3f1b9c2e0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('pitch', sa.String(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('projects', 'pitch')
