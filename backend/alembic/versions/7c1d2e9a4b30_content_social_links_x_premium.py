"""content social links remember X Premium

content_social_links.has_x_premium: whether PostBridge last reported the
linked account on X Premium, which lifts X's limit from 280 characters to
25,000. Kept on the link so drafting, the pre-publish review and the preview
know the limit without calling PostBridge; every account listing refreshes
it (service/social_accounts.py). False for every existing row until the next
listing, which only means a Premium account drafts short once.

Hand-written: one boolean column. Batch mode because the desktop sidecar runs
this on SQLite (db/migrate.py). CI's `alembic check` compares it with the
model.

Revision ID: 7c1d2e9a4b30
Revises: e1ebd2525648
Create Date: 2026-10-01 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '7c1d2e9a4b30'
down_revision = 'e1ebd2525648'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('content_social_links') as batch:
        batch.add_column(
            sa.Column('has_x_premium', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('content_social_links') as batch:
        batch.drop_column('has_x_premium')
