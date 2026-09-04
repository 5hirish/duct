"""record whether a credential may leave the machine it was entered on

Revision ID: e7b2c9d40a15
Revises: d5f8a3c71b04
Create Date: 2026-09-04 00:00:00.000000

Duct runs the same backend in two places now — a deployment, and a sidecar
inside the desktop app — and the sidecar can be pointed at either its own
SQLite or a shared Postgres. So "where does this credential live" stopped
having a stable answer, and the UI was inferring one from whether a sidecar
happened to serve the request. That inference is wrong in exactly the case that
matters: a sidecar talking to staging stores nothing on the machine it runs on,
and telling someone their credentials never left the laptop when they are in a
shared database is the wrong direction to be wrong in.

`db.session.storage_location()` reports where a row *is*, read from the database
dialect. This column records where the user said it may *be*. Both are needed —
the first is a fact that changes the moment the process is repointed, the second
is an intent that travels with the row and can be enforced when it is written.

Default `server`: a credential no scheduled brief can reach is useless for most
of what Duct does, and every row predating this migration was stored
server-side by definition, so the default is also the truth about them.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'e7b2c9d40a15'
down_revision = 'd5f8a3c71b04'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'connector_credentials',
        sa.Column('residency', sa.String(), nullable=False, server_default='server'),
    )


def downgrade() -> None:
    op.drop_column('connector_credentials', 'residency')
