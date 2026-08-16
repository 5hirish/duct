"""Portable column types shared by the SQLModel tables.

The deployment runs Postgres; the desktop build (`DUCT_LOCAL`) runs SQLite in the
user's data dir. `JSONB` is a Postgres-only type and fails to compile on SQLite
with "can't render element of type JSONB", so JSON columns are declared through
a variant instead: generic `JSON` by default, still `JSONB` on Postgres.

Because the Postgres rendering is unchanged, this is invisible to the existing
schema and produces no Alembic autogenerate diff.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def json_column() -> sa.types.TypeEngine:
    """JSON column type: `JSONB` on Postgres, generic `JSON` elsewhere.

    Call it per column rather than sharing one instance — SQLAlchemy binds a type
    instance to the Column it is attached to.
    """
    return sa.JSON().with_variant(JSONB(astext_type=sa.Text()), "postgresql")
