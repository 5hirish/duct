"""Shared transport for the sync reporting connectors.

Scope: the credential-per-call, dict-returning clients the insights pipeline
drives through ``asyncio.to_thread`` — Apple Ads, Meta Ads, OpenAI Ads, Stripe,
RevenueCat, and whatever lands next. Deliberately NOT for ``service/apify`` or
``service/post_bridge``: those are async, hold a long-lived ``AsyncClient``,
return Pydantic models and have no retry needs. Forcing both families through
one abstraction would serve neither.

What differs per vendor is real and stays in the vendor module: auth headers,
query encoding, error envelopes, how long to wait after a throttle. What does
*not* differ is the loop around them — issue, classify, sleep, retry, give up —
and five copies of that loop had already drifted on whether a 204 is a success,
whether an empty 200 body is an error, and whether "retries exhausted" raises
the vendor's error type or a bare one.

Adding a connector means declaring an ``Endpoint`` and an ``ApiError`` subclass;
the loop comes for free.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

# Statuses worth a second attempt on any vendor: rate limit + transient 5xx.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

# `status` sentinel for "the request never completed" — DNS, TLS, timeout, reset.
TRANSPORT_FAILED = 0


class ApiError(Exception):
    """One vendor call failed, after retries.

    ``status`` is the HTTP status, or ``TRANSPORT_FAILED`` (0) when the request
    never reached the vendor. Subclasses unpack the vendor's error envelope by
    overriding ``parse``, and offer a fix through ``hint``.
    """

    def __init__(self, status: int, body: str, url: str = "") -> None:
        self.status = status
        self.body = body or ""
        self.url = url
        self.summary = self.parse(self.body) or self.body[:300]
        super().__init__(f"HTTP {status} — {self.summary}")

    def parse(self, body: str) -> str:
        """The vendor's error envelope reduced to one human-readable line."""
        return ""

    def hint(self) -> str:
        """What the operator should do about it, when there's a known answer."""
        return ""

    @property
    def code(self) -> int:
        """Alias for ``status`` — several connectors' call sites read ``.code``."""
        return self.status

    @property
    def transport_failed(self) -> bool:
        return self.status == TRANSPORT_FAILED


class RetryPolicy:
    """How many attempts a vendor gets, and how long it waits between them.

    Doubling from ``first``, capped at ``cap``. Subclass and override ``delay``
    when a vendor needs more than that — Meta's throttles refill on a sliding
    hour and want minutes, RevenueCat sends its own ``backoff_ms``.
    """

    def __init__(
        self,
        attempts: int = 5,
        statuses: Iterable[int] = RETRYABLE_STATUSES,
        first: float = 2.0,
        cap: float = 30.0,
    ) -> None:
        self.attempts = attempts
        self.statuses = frozenset(statuses)
        self.first = first
        self.cap = cap

    def delay(self, error: ApiError, attempt: int) -> float | None:
        """Seconds to wait before the next attempt, or None to give up now.

        ``attempt`` is 0-based, so the last one never sleeps. A request that
        never completed is always worth retrying; a status only when listed.
        """
        if attempt >= self.attempts - 1:
            return None
        if error.transport_failed or error.status in self.statuses:
            return min(self.cap, self.first * (2 ** attempt))
        return None


class Pacer:
    """Process-wide floor between calls to a tight-budget endpoint.

    Self-pacing beats discovering the budget through 429s: RevenueCat's charts
    allow 25/min against 480/min elsewhere, so only the charts calls pace.
    Shared across threads because the vendor's budget is per-account, not
    per-thread.
    """

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            gap = time.monotonic() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            self._last = time.monotonic()


@dataclass(frozen=True)
class Endpoint:
    """A vendor's API root plus its transport rules.

    Declare one per connector at module level, then call ``request`` from the
    vendor's own ``api()`` wrapper — that wrapper keeps ownership of auth
    headers and stays the module's public surface.
    """

    base_url: str
    error_cls: type[ApiError] = ApiError
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout: float = 180.0
    #: Statuses treated as success. An empty body on any of them yields {}.
    success: frozenset[int] = frozenset({200, 201, 204})
    #: Optional per-vendor query encoding (Stripe's `a[b]=c`, Meta's JSON values).
    encode: Callable[[Mapping[str, Any] | None], Any] | None = None

    def url_for(self, path: str) -> str:
        """Absolute URLs pass through — pagination cursors often arrive as one."""
        return path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"

    def request(
        self,
        path: str,
        *,
        headers: Mapping[str, str],
        method: str = "GET",
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        pacer: Pacer | None = None,
    ) -> dict:
        """Issue one call, retrying per the policy. Returns the parsed body.

        Raises ``error_cls`` — the vendor's own subclass, so callers can branch
        on its unpacked fields. When the retry budget runs out the *last real*
        error is what surfaces, not a synthetic one: a pull that dies after five
        503s should still tell you it was a 503.
        """
        url = self.url_for(path)
        query = self.encode(params) if self.encode is not None else params

        for attempt in range(self.retry.attempts):
            if pacer is not None:
                pacer.wait()
            try:
                resp = httpx.request(
                    method, url, params=query, json=json, data=data,
                    headers=dict(headers), timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                error = self.error_cls(TRANSPORT_FAILED, f"request failed: {exc}", url)
                delay = self.retry.delay(error, attempt)
                if delay is None:
                    raise error from exc
                time.sleep(delay)
                continue

            if resp.status_code in self.success:
                # 204s and some vendors' 200s carry no body at all.
                return resp.json() if resp.text.strip() else {}

            error = self.error_cls(resp.status_code, resp.text, url)
            delay = self.retry.delay(error, attempt)
            if delay is None:
                raise error
            time.sleep(delay)

        # Unreachable with a well-behaved policy — the last attempt's delay() is
        # None, so the loop raises the real error rather than this placeholder.
        # Kept as a backstop for attempts <= 0 or a subclass that forgets to stop.
        raise self.error_cls(TRANSPORT_FAILED, "retries exhausted", url)
