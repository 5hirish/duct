"""merge lead_magnets and content heads

Revision ID: 03831564fab0
Revises: b2c9f4d8e103, d52f7b1ea4c8
Create Date: 2026-06-04 00:07:08.608457
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '03831564fab0'
down_revision = ('b2c9f4d8e103', 'd52f7b1ea4c8')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

