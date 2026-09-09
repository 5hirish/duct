"""A fixed-window counter for the two endpoints anyone on the internet can call.

Guest creation and the crawl prefetch run before sign-in, so nothing else
stands between a script and a database row or a crawl of someone's site. A
per-key window is enough: the cost we are bounding is ours (a row, a crawl),
not the caller's, and the honest failure is a 429 with a retry time rather
than a Turnstile the desktop shell cannot render.

In-process on purpose. A multi-replica deployment gets one window per
replica, which is a looser limit, not a wrong one; the moment the miss rate
says so this moves to the database, and not before.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class RateLimit:
    """``limit`` events per ``window_seconds`` for each key."""

    limit: int
    window_seconds: float

    def __post_init__(self) -> None:
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        """Record one event for ``key``.

        Returns ``(allowed, retry_after_seconds)``; ``retry_after`` is zero when
        allowed.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            started, count = self._hits.get(key, (now, 0))
            if now - started >= self.window_seconds:
                started, count = now, 0
            if count >= self.limit:
                return False, max(0.0, self.window_seconds - (now - started))
            self._hits[key] = (started, count + 1)
            if len(self._hits) > 10_000:
                self._prune(now)
        return True, 0.0

    def _prune(self, now: float) -> None:
        stale = [k for k, (started, _) in self._hits.items() if now - started >= self.window_seconds]
        for k in stale:
            self._hits.pop(k, None)
