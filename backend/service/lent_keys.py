"""Provider keys a person's open app lends to their own scheduled runs.

A desktop app keeps its model keys in the OS keychain and sends them only on
requests, so a run nobody starts (service/schedules.py) has none to spend and
would sit at "Needs you: no saved model key" for exactly the people the
desktop build exists for. The app already calls the memory catch-up with its
header keys when it opens and every half hour after (``routes/memory.py``);
that same call lends them here.

Three rules, each the reason this is safe:

* **In memory only, never stored.** A process restart forgets them, which is
  the same as the app being closed: nobody is lending.
* **They expire.** ``LEND_FOR`` is a little longer than the app's half-hour
  ping, so keys go stale soon after the app closes or the tab goes away.
* **Spent only on the lender's own schedules.** A run acts as its creator, so
  the creator's keys are the only ones it may borrow; a teammate's open app
  never pays for someone else's schedule.

Plan tokens (a ChatGPT sign-in) are never lent, as with memory: a structured
background call cannot spend them.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from uuid import UUID

from utils.dates import utcnow

LEND_FOR = timedelta(minutes=45)

_lock = threading.Lock()
_held: dict[UUID, tuple[dict, datetime]] = {}


def _spendable(keys: dict | None) -> dict:
    """The keys a background call can spend: real API keys, never a plan token."""
    from service.memory_consolidation import _spendable as memory_spendable

    keys = dict(keys or {})
    return keys if keys and memory_spendable(keys) else {}


def lend(user_id: UUID | None, keys: dict | None, *, now: datetime | None = None) -> bool:
    """Hold ``keys`` for ``user_id`` until ``LEND_FOR`` from now. True when held."""
    if user_id is None:
        return False
    spendable = _spendable(keys)
    if not spendable:
        return False
    with _lock:
        _held[user_id] = (spendable, (now or utcnow()) + LEND_FOR)
    return True


def borrowed(user_id: UUID | None, *, now: datetime | None = None) -> dict | None:
    """The keys ``user_id`` lent, while they last; None when nobody is lending."""
    if user_id is None:
        return None
    with _lock:
        held = _held.get(user_id)
        if held is None:
            return None
        keys, until = held
        if until <= (now or utcnow()):
            _held.pop(user_id, None)
            return None
        return dict(keys)


def forget(user_id: UUID | None = None) -> None:
    """Drop one person's lent keys, or everyone's (tests)."""
    with _lock:
        if user_id is None:
            _held.clear()
        else:
            _held.pop(user_id, None)
