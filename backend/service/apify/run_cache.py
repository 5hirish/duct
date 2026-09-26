"""Reuse a recent identical actor run instead of paying for a second one.

The actor run is the metered, minutes-long part of a Discover search; reading
its dataset afterwards is free. Searches repeat — the same hashtags twice in an
afternoon, a reload while a run is going, a second project on the same niche —
and each repeat used to start and bill a fresh run. So a run is remembered by
its actor and canonical input for ``RUN_REUSE_TTL_SECONDS``, and an identical
start inside that window gets the remembered run back: still running, the
caller joins it; finished, its dataset is served as it is.

Keyed on actor and input, not on project. The results are public TikTok posts,
so a second project searching the same tags learns nothing about the first.

In process and deliberately not durable. The API runs one replica with one
worker (``railway.json``), so one dict serves every request; a restart forgets
it and the worst case is one run we could have reused. A second replica would
want this in the database — the key and the TTL would not change. Two identical
starts inside the same second both miss and both run; the Discover button is
disabled while a run is in flight, which is what makes that a non-case.

This sits above ``ApifyClient`` rather than inside it: the client is a thin
transport, and "should this run happen at all" is a product decision.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from service.apify.client import ApifyAPIError, ApifyClient
from service.apify.schema import ApifyRun, ApifyRunStatus

# Long enough to cover "run it again after lunch", short enough that a trend
# search still reads the day's posts. TikTok signs the image URLs in a dataset
# for hours, so a reused run's covers still load.
RUN_REUSE_TTL_SECONDS = 30 * 60

# Every distinct search adds one entry for the TTL. The cap only matters if
# something starts hundreds of unique runs in half an hour, and then the oldest
# are the least likely to be repeated.
MAX_REMEMBERED_RUNS = 256

# A run in one of these states has no dataset worth joining, so an identical
# search starts over instead of inheriting the failure for the rest of the TTL.
_UNUSABLE = frozenset({
    ApifyRunStatus.FAILED,
    ApifyRunStatus.ABORTING,
    ApifyRunStatus.ABORTED,
    ApifyRunStatus.TIMING_OUT,
    ApifyRunStatus.TIMED_OUT,
})


def run_key(actor_id: str, payload: dict[str, Any]) -> tuple[str, str]:
    """The identity of a search: the actor, and its input with keys sorted.

    ``user/actor`` and ``user~actor`` name one actor (the Store writes the
    first, the API the second), so they share a key. List order is kept: the
    actor may treat hashtag order as priority.
    """
    actor = actor_id.strip().replace("/", "~")
    canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
    return actor, canonical


class RunCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = RUN_REUSE_TTL_SECONDS,
        max_entries: int = MAX_REMEMBERED_RUNS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._runs: dict[tuple[str, str], tuple[float, str]] = {}

    async def start(
        self, client: ApifyClient, actor_id: str, payload: dict[str, Any]
    ) -> tuple[ApifyRun, bool]:
        """Return ``(run, reused)``: a live remembered run, or a newly started one."""
        key = run_key(actor_id, payload)
        remembered = self._runs.get(key)
        if remembered is not None:
            started_at, run_id = remembered
            if self._clock() - started_at < self._ttl:
                try:
                    run = await client.get_run(run_id)
                except ApifyAPIError:
                    # Expired or unreachable on Apify's side: a fresh run is
                    # the answer that cannot be wrong, only more expensive.
                    run = None
                if run is not None and run.status not in _UNUSABLE:
                    return run, True
            del self._runs[key]
        run = await client.start_run(actor_id, payload)
        self._remember(key, run.id)
        return run, False

    def _remember(self, key: tuple[str, str], run_id: str) -> None:
        now = self._clock()
        for stale in [k for k, (at, _) in self._runs.items() if now - at >= self._ttl]:
            del self._runs[stale]
        while len(self._runs) >= self._max:
            # Insertion order is start order, so the first key is the oldest.
            del self._runs[next(iter(self._runs))]
        self._runs[key] = (now, run_id)


# The process-wide instance the Discover route uses.
apify_runs = RunCache()
