"""Which of this caller's provider accounts are out of quota right now.

A 429 that the retry loop gave up on is a fact worth keeping for a few minutes.
Without it the next run resolves to the same tier, spends the same four
attempts, and dies the same way — while the Standard model the user picked, on
a different vendor with its own untouched quota, sits in their tier map
unreached.

**Cool down a credential, never a provider.** Duct is multi-tenant with
bring-your-own keys: a 429 on one customer's Anthropic key says nothing about
another's, because they are different accounts with different limits. Keying
this by provider alone would let one heavy user route every other customer off
Anthropic. So entries are keyed by ``(identity, provider)`` where ``identity``
is a hash of the key — the same rule ``tiers.resolve_tier_model`` states for
``reachable``, which takes per-request credentials as a parameter rather than
reaching for globals.

Provider-level rather than per-model, because the window that actually bites
(Anthropic's five-hour, OpenAI's plan quota) is an account property, and the
consumer is the tier ladder, which resolves a tier *to a provider*. Not the
model for a second reason too: ``ModelFallbackMiddleware`` sits outside the
retry middleware that records here, so by the time a limit is final the model
being served may not be the one this middleware was built for. The provider is
correct for every model in the chain — ``MODEL_FALLBACK`` never crosses one.

**Deliberately not durable.** A cooldown is a hint, not a correctness boundary:
the worst case on a fresh worker is one wasted 429 that records its own
cooldown. That is cheaper than a database write on the hot path of every rate
limit, and it keeps the desktop sidecar identical to the server. The API is two
functions rather than an exposed dict precisely so a Redis or table-backed
implementation can replace the storage without touching either caller.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import threading
import time
from hashlib import sha256

from agents.models import Provider

logger = logging.getLogger(__name__)

# What to assume when the provider did not say. Long enough that the next run
# in a burst does not repeat the failure, short enough that a user who tops up
# their account is not benched for the afternoon.
DEFAULT_COOLDOWN_SECONDS = 300.0

# The ceiling, whatever the provider asked for. A `retry-after` of a day is
# either a mistake or a suspension; either way, benching a tier for a day on
# one header is worse than re-learning the limit an hour later.
MAX_COOLDOWN_SECONDS = 3600.0

# Bounded so a server seeing many keys cannot grow this without limit. Swept on
# write, and over the cap the entries expiring soonest are dropped first —
# those are the ones whose loss costs least.
MAX_ENTRIES = 2048


#: Salt for the identity below, drawn once per process.
#:
#: A bare digest of a key is reversible by anyone who can guess the key and run
#: the same hash — so an identity that escaped into a log would confirm a guess
#: rather than resist it. Keyed hashing removes that oracle and makes the
#: docstring's "safe to log" true without a footnote.
#:
#: Per-process, and regenerated on restart, which costs exactly nothing: the
#: store it keys is in-process and deliberately not durable, so an identity has
#: never needed to mean the same thing in two processes or across a restart.
_SALT = secrets.token_bytes(32)


def credential_identity(api_key: str) -> str:
    """A correlation handle for a key, safe to hold in memory and to log.

    The key itself never enters this module's storage. Returns "" for an empty
    key so an unauthenticated caller cannot collide with a real one.
    """
    key = (api_key or "").strip()
    if not key:
        return ""
    return hmac.new(_SALT, key.encode(), sha256).hexdigest()[:16]


_lock = threading.Lock()
#: (identity, provider) → the monotonic time the cooldown lapses.
_entries: dict[tuple[str, Provider], float] = {}


def note_exhausted(
    identity: str,
    provider: Provider,
    *,
    seconds: float | None = None,
    now: float | None = None,
) -> None:
    """Record that ``identity``'s ``provider`` account is out of quota.

    ``seconds`` is the provider's own reset window when it sent one
    (``errors.retry_after_seconds``), clamped into a sane range. A caller with
    no identity — no key we can attribute this to — records nothing rather than
    cooling down an empty-string bucket every other request would then share.
    """
    if not identity:
        return
    clock = time.monotonic() if now is None else now
    window = DEFAULT_COOLDOWN_SECONDS if not seconds or seconds <= 0 else float(seconds)
    window = min(window, MAX_COOLDOWN_SECONDS)
    with _lock:
        _entries[(identity, provider)] = clock + window
        # Swept after the insert, not before: sweeping first leaves the cap
        # one over on every write, and "bounded" that is always breached by one
        # is not a bound anyone can reason about.
        _sweep(clock)
    logger.info("quota: %s cooled down for %.0fs", provider.value, window)


def cooling(identity: str, *, now: float | None = None) -> frozenset[Provider]:
    """The providers ``identity`` is currently out of quota on.

    Empty for an unknown identity, which is what makes this safe to call
    unconditionally from the resolver.
    """
    if not identity:
        return frozenset()
    clock = time.monotonic() if now is None else now
    with _lock:
        return frozenset(
            provider
            for (owner, provider), expires_at in _entries.items()
            if owner == identity and expires_at > clock
        )


def cooling_seconds(identity: str, *, now: float | None = None) -> dict[Provider, float]:
    """How long each cooled provider has left, in seconds.

    A duration rather than a timestamp, for the reason ``MODEL_RETRYING``'s
    ``retry_in`` gives: the client anchors it to its own clock on receipt, so a
    skewed server clock cannot show a countdown that is already over.
    """
    if not identity:
        return {}
    clock = time.monotonic() if now is None else now
    with _lock:
        return {
            provider: expires_at - clock
            for (owner, provider), expires_at in _entries.items()
            if owner == identity and expires_at > clock
        }


def _sweep(now: float) -> None:
    """Drop expired entries, then the soonest-expiring ones if still over cap.

    Caller holds the lock.
    """
    for key in [k for k, expires_at in _entries.items() if expires_at <= now]:
        del _entries[key]
    if len(_entries) <= MAX_ENTRIES:
        return
    ordered = sorted(_entries.items(), key=lambda kv: kv[1])
    for key, _ in ordered[: len(_entries) - MAX_ENTRIES]:
        del _entries[key]


def reset() -> None:
    """Forget every cooldown. For tests, and for a sidecar restarting clean."""
    with _lock:
        _entries.clear()
