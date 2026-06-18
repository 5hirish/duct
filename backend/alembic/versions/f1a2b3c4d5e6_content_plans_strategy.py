"""content_plans.strategy — long-term narrative arc for the content planner agent

Adds a JSONB `strategy` column to content_plans. Written by the content_planner
agent's submit_plan; holds the narrative arc, sequencing rationale, and
content-type mix so each weekly plan refresh can continue the prior thread.

Additive + reversible.

Revision ID: f1a2b3c4d5e6
Revises: b3d7e1f4a92c
Create Date: 2026-06-18

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f1a2b3c4d5e6"
down_revision = "b3d7e1f4a92c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_plans",
        sa.Column(
            "strategy",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("content_plans", "strategy")
