"""record the OAuth scopes a connector was actually granted

Revision ID: b6e73f2c0a91
Revises: a4d18e5c26bf
Create Date: 2026-09-02 00:00:00.000000

Until now Duct asked for scopes and read back only the refresh token, so
"connected" meant "the exchange succeeded" and nothing more. Google's consent
screen lets people untick individual boxes — GA4 asks for `analytics.edit`
alongside `analytics.readonly`, GTM asks for three — and a connector granted
less than it asked for looked identical to one granted everything, right up
until a call 403'd.

One column, not a table: scopes are not a secret, they are one short
space-separated string per credential (the shape OAuth itself uses), and the
data-source inventory reads them on every page load. Storing them inside
`credentials_enc` would mean decrypting every row to answer "is this fully
authorized?".

Empty means **unknown**, not "none granted": every row that predates this
migration was authorized without our recording what it got. The reader
(`service/connector_scopes.scope_status`) reports that as its own state rather
than assuming the happy answer.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'b6e73f2c0a91'
down_revision = 'a4d18e5c26bf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default rather than a backfill: existing rows correctly become
    # "unknown", and NOT NULL keeps the reader from having to handle None as a
    # third spelling of empty.
    op.add_column(
        'connector_credentials',
        sa.Column('granted_scopes', sa.String(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('connector_credentials', 'granted_scopes')
