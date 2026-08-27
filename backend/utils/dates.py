"""Timezone-aware datetime helpers.

Every timestamp Duct persists or serialises is UTC-aware — naive datetimes
compare and serialise inconsistently across SQLite (desktop) and Postgres
(Railway), so the rule is: construct with ``utcnow()``, never
``datetime.now()``/``datetime.utcnow()``.

Leaf module: standard library only, so ``models/`` can import it without a
cycle (SQLModel ``default_factory=utcnow`` is the main caller).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return utcnow().isoformat()


def parse_iso(value: Any, *, default: datetime | None = None) -> datetime | None:
    """Parse an ISO 8601 string (``Z`` suffix included) into an aware UTC datetime.

    Returns ``default`` for anything unparseable, so callers handling untrusted
    input (query params, third-party payloads) don't need their own try/except.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return default
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def last_n_days(days: int, end: date | None = None) -> tuple[str, str]:
    """``(start, end)`` ISO dates for the last ``days`` days, inclusive.

    ``end`` defaults to yesterday — ad platforms only settle a day's numbers
    after it closes, so today is always partial.
    """
    end = end or (date.today() - timedelta(days=1))
    return (end - timedelta(days=days - 1)).isoformat(), end.isoformat()
