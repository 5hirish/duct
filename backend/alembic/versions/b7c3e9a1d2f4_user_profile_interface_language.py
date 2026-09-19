"""user profile interface language

The language the app's interface is rendered in, as a catalogue tag ("es",
"pt-BR", ...) or '' for "follow the browser". Server-owned like the rest of the
profile so a second device opens in the language the first one chose. Distinct
from ``communication_language``, which is a model instruction and accepts any
language; this one accepts only the languages the app has translations for.

Revision ID: b7c3e9a1d2f4
Revises: dda6dccbdee4
Create Date: 2026-09-19 10:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b7c3e9a1d2f4'
down_revision = 'dda6dccbdee4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_profile',
        sa.Column('interface_language', sa.String(), server_default='', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('user_profile', 'interface_language')
