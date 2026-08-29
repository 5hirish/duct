"""Portable column types shared by the SQLModel tables.

The deployment runs Postgres; the desktop build (`DUCT_LOCAL`) runs SQLite in the
user's data dir. The two disagree about types in ways that are easy to miss,
because every test and every deploy exercises Postgres and only a user's laptop
exercises SQLite. Declare columns through the helpers here rather than the raw
types, and the difference stops being the caller's problem:

* `json_column()` — `JSONB` is Postgres-only and fails to compile on SQLite with
  "can't render element of type JSONB".
* `utc_datetime()` — SQLite silently discards the timezone, so reads come back
  naive and comparisons against an aware `utcnow()` raise `TypeError`.

Both render on Postgres exactly as the raw types did, so this is invisible to the
existing schema and produces no Alembic autogenerate diff.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def json_column() -> sa.types.TypeEngine:
    """JSON column type: `JSONB` on Postgres, generic `JSON` elsewhere.

    Call it per column rather than sharing one instance — SQLAlchemy binds a type
    instance to the Column it is attached to.
    """
    return sa.JSON().with_variant(JSONB(astext_type=sa.Text()), "postgresql")


class _UTCDateTime(sa.types.TypeDecorator):
    """`TIMESTAMPTZ` that stays timezone-aware on SQLite too.

    Postgres round-trips an aware datetime unchanged. SQLite has no timestamp
    type: SQLAlchemy stores the value with a format string that has no offset
    field, so the `timezone=True` is silently dropped on write and every read
    comes back *naive*. Any `row.ts <= utcnow()` then raises
    `TypeError: can't compare offset-naive and offset-aware datetimes` — a
    desktop-only crash in code the deployment exercises constantly (it cost us
    the whole desktop sign-in: the OAuth state expiry check on the callback).

    So normalise at the type boundary rather than at each comparison: bind
    converts to UTC, result attaches UTC to anything naive. Rows written before
    this existed read back correctly, since they were always UTC in substance.
    """

    impl = sa.DateTime
    cache_ok = True

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("timezone", True)
        super().__init__(*args, **kwargs)

    @property
    def python_type(self) -> type:
        """`TypeEngine.python_type` raises by default and `TypeDecorator` does not
        proxy it to the impl, which leaves the column looking like it holds no
        Python type at all — enough to make schema introspection skip it."""
        return datetime

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utc_datetime() -> sa.types.TypeEngine:
    """Aware-UTC timestamp column. Renders as `TIMESTAMPTZ`, so no schema diff.

    Call it per column — SQLAlchemy binds a type instance to its Column.
    """
    return _UTCDateTime()
