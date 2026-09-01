"""pinned on artifacts and agent_conversations — keeping things on the desk

The insights desk lists threads and the documents they produced. Pinning floats
a row to the top of its own list and does nothing else: it is a display order,
not a permission, not a lifecycle state.

Modelled on ``project_memories.pinned``, which has done the same job since
a4e1c7d2b953 and is read by the retrieval ranking in service/memory.py. Same
shape here, so there is one idea of "pinned" across the product.

On artifacts the flag is per *group*, not per version: the library lists the
newest version of each group, so a pin set on one version would vanish the next
time the agent wrote one. Writers set it on every row sharing the group_id.

Revision ID: c7e4b2a19d63
Revises: b8f3d1e6a274
Create Date: 2026-09-01 11:20:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'c7e4b2a19d63'
down_revision = 'b8f3d1e6a274'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'artifacts',
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'agent_conversations',
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('agent_conversations', 'pinned')
    op.drop_column('artifacts', 'pinned')
