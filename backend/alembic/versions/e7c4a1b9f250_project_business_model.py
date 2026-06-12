"""projects: business_model column

Revision ID: e7c4a1b9f250
Revises: 03831564fab0
Create Date: 2026-06-04 00:00:00.000000

The onboarding "Company" step captures a business_model (e.g. B2C, B2B,
marketplace) alongside name and industry. It lives in the local project
profile but had no home on the persisted `projects` table; this adds it
so the full company profile round-trips through /api/user/projects.

The existing `url` column holds the company website_url — no new column
needed for that.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'e7c4a1b9f250'
down_revision = '03831564fab0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('business_model', sa.String(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('projects', 'business_model')
