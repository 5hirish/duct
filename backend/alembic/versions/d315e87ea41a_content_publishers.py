"""content publishers: a post and a linked account name their scheduler

Revision ID: d315e87ea41a
Revises: 4140bc5d250f
Create Date: 2026-11-02 19:47:14.725250

Schedulers became connectors (service/publishers/): PostBridge and Zernio,
whichever the person connects. A post's ids at its scheduler were columns
named for PostBridge, so they are renamed, not dropped and re-added, which
would lose every scheduled post's link to its queue; and each post and
linked account gains the scheduler that holds it. Every row written before
this one went through PostBridge, so that is what they are backfilled to.

A linked account is unique per scheduler now: two schedulers can number
their accounts the same. SQLite-safe (batch mode), because the desktop
sidecar runs this too (db/migrate.py).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd315e87ea41a'
down_revision = '4140bc5d250f'
branch_labels = None
depends_on = None

_POST_BRIDGE = "post_bridge"


def upgrade() -> None:
    with op.batch_alter_table('content_posts') as batch:
        batch.add_column(sa.Column('publisher', sa.String(), server_default='', nullable=False))
        batch.alter_column('post_bridge_post_id', new_column_name='publisher_post_id')
        batch.alter_column('post_bridge_result_id', new_column_name='publisher_metrics_id')
    op.execute(sa.text(
        "UPDATE content_posts SET publisher = :pb WHERE publisher_post_id <> ''"
    ).bindparams(pb=_POST_BRIDGE))

    with op.batch_alter_table('content_social_links') as batch:
        batch.add_column(sa.Column('publisher', sa.String(), server_default='', nullable=False))
        batch.drop_constraint('uq_content_social_links_project_account', type_='unique')
        batch.create_unique_constraint(
            'uq_content_social_links_project_publisher_account',
            ['project_id', 'publisher', 'external_account_id'],
        )
    op.execute(sa.text("UPDATE content_social_links SET publisher = :pb").bindparams(pb=_POST_BRIDGE))


def downgrade() -> None:
    # A link to another scheduler's account has nowhere to go in the old shape.
    op.execute(sa.text("DELETE FROM content_social_links WHERE publisher <> :pb").bindparams(pb=_POST_BRIDGE))
    with op.batch_alter_table('content_social_links') as batch:
        batch.drop_constraint('uq_content_social_links_project_publisher_account', type_='unique')
        batch.create_unique_constraint(
            'uq_content_social_links_project_account', ['project_id', 'external_account_id'],
        )
        batch.drop_column('publisher')

    with op.batch_alter_table('content_posts') as batch:
        batch.alter_column('publisher_metrics_id', new_column_name='post_bridge_result_id')
        batch.alter_column('publisher_post_id', new_column_name='post_bridge_post_id')
        batch.drop_column('publisher')
