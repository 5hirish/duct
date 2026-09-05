"""record which entity inside an account a project actually reads

Revision ID: d5f8a3c71b04
Revises: b6e73f2c0a91
Create Date: 2026-09-04 00:00:00.000000

A connector credential reaches many things: one Search Console sign-in covers
every property the user verified, one GA4 sign-in every property they can read.
Binding a project to the *credential* therefore never said which of them the
project meant, and the picker had nothing to show but "Account default" over a
row with no name.

Two columns on the binding rather than a row per entity. The alternative —
one `connector_credentials` row per property, the way manual connectors store
one per account — would duplicate the same encrypted refresh token once per
site, and a user with thirty verified properties would get thirty copies of one
secret to rotate.

Empty means **not chosen**, which is a legitimate resting state: the agent asks
when it needs one. It deliberately does not mean "use the only one available" —
inferring that silently picks for the user and becomes wrong the moment a
second property appears.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'd5f8a3c71b04'
down_revision = 'b6e73f2c0a91'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default '' rather than nullable: the reader then has one spelling
    # of "unset" to handle instead of two.
    op.add_column(
        'project_connectors',
        sa.Column('entity_id', sa.String(), nullable=False, server_default=''),
    )
    op.add_column(
        'project_connectors',
        sa.Column('entity_name', sa.String(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('project_connectors', 'entity_name')
    op.drop_column('project_connectors', 'entity_id')
