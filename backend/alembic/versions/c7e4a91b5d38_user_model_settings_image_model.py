"""user_model_settings: which model draws

The Images row on the settings page was read-only — it reported whichever of
your keys the resolver reached first, in ``IMAGE_PROVIDER_ORDER``. That is a
fine default and a poor ceiling: a Gemini key reaches three image models and
the user could only ever have the Flash one.

Nullable-free with a server default of '', because every existing row means
exactly that: nobody picked, resolve in the usual order. So this migration
changes no behaviour for anyone until they choose something.

Revision ID: c7e4a91b5d38
Revises: 04781f04eb5e
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7e4a91b5d38"
down_revision = "04781f04eb5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_model_settings",
        sa.Column("image_model", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("user_model_settings", "image_model")
