"""Lossless compaction for oversized tool payloads.

A Duct tool returns a connector's rows and the brief quotes the numbers in
them, so the only compression allowed here is the kind that reads back value
for value: a homogeneous array becomes a typed CSV carrying a schema header,
with every row kept, in order, and nothing rounded or summarised. The
statistical path — which keeps a sample of rows and a hash for the rest — is
refused outright through ``lossless_only``, because a plausible number that is
not in the customer's account is the worst thing this product can emit.

Why compact at all, when the safest thing is to send the payload untouched: the
alternative was never "send everything". It is
``agents/insights/data_tools.py::_truncate``, which cuts an oversized payload
mid-structure at ``MAX_RESPONSE_CHARS``. Measured on a 900-row search-terms
pull, that discards about two thirds of the numbers and says so only in a note
the model has no way to act on, having already lost the rows. Compaction gets
the same payload under the same limit with all 900 rows intact — so this is a
fidelity fix that happens to save tokens, not a token saving that costs
fidelity.

The lossless contract is verified per payload rather than trusted. It has to
be: ``lossless_only`` does not reach every path — an array of identical
*strings* is still collapsed by a separate adaptive branch (200 items became 2,
found by an existing test in tests/test_insights_data.py, not by a review) —
and a payload that silently loses rows is exactly the failure this module
exists to prevent. So every compaction is checked structurally before it is
returned, and anything that does not check out is discarded in favour of the
original bytes. That check is also what makes the pin in pyproject.toml a
belt-and-braces measure rather than the only defence against a release that
changes what compression means.

A missing dependency is not an error. Self-host builds and the PyInstaller
sidecar may ship without the Rust extension, and a compressor that cannot load
must degrade to the payload we would have sent anyway rather than fail a fetch.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# The header a folded array carries: ``[900]{col:type,…}`` followed by the rows.
# Its count is the compactor's own claim about how many rows it wrote, which is
# what makes the verification below cheap — no need to parse the CSV itself.
_ROW_HEADER = re.compile(r"^\[(\d+)\]\{")


@lru_cache(maxsize=1)
def _crusher() -> Any | None:
    """The compactor, or ``None`` where it is not installed.

    Cached rather than rebuilt per call: construction is cheap but not free,
    and one shared instance is safe to drive from several threads at once
    (verified concurrently before this landed — identical output across 24
    simultaneous calls on 8 threads).
    """
    try:
        from headroom import SmartCrusher, SmartCrusherConfig
    except Exception:  # noqa: BLE001 — absent or unloadable, both mean "no"
        logger.info("compaction: headroom unavailable, payloads pass through")
        return None
    # Two identical rows are two rows. Dedup is defensible for a log tail and
    # wrong for an analytics pull, where the duplicate is a second real record
    # and the count is itself a number someone quotes.
    config = SmartCrusherConfig(dedup_identical_items=False)
    return SmartCrusher(config=config, lossless_only=True)


def _lossless(before: Any, after: Any) -> bool:
    """Whether ``after`` still carries everything ``before`` did.

    Containers may change shape — an array of records is allowed to arrive as a
    rendered table — but nothing may go missing on the way. Values are compared
    directly, because a fold that rewrites a value rather than its container is
    not a fold.
    """
    if isinstance(before, dict):
        return (
            isinstance(after, dict)
            and before.keys() == after.keys()
            and all(_lossless(before[k], after[k]) for k in before)
        )
    if isinstance(before, list):
        if isinstance(after, list):
            return len(before) == len(after) and all(
                _lossless(b, a) for b, a in zip(before, after)
            )
        # Folded to a table: trust only a header whose declared row count
        # matches, which is precisely the claim the string-dedup path cannot
        # make.
        if isinstance(after, str):
            header = _ROW_HEADER.match(after)
            return bool(header) and int(header.group(1)) == len(before)
        return False
    return before == after


def compact(body: str) -> str:
    """Return ``body`` losslessly compacted, or ``body`` unchanged.

    Never raises and never grows the payload: a compactor that finds no
    homogeneous array to fold returns the input, and anything unexpected is
    logged and swallowed. Both outcomes leave the caller with a payload it can
    still send, which is why callers do not need to handle a failure mode.
    """
    crusher = _crusher()
    if crusher is None or not body:
        return body
    try:
        out = crusher.crush(body).compressed
    except Exception:  # noqa: BLE001 — a payload is worth more than a stack trace
        logger.warning("compaction: crush failed, sending payload whole", exc_info=True)
        return body
    # Compaction that made things bigger is compaction we do not want. It
    # should not happen on tabular JSON, but the check is one comparison and
    # the alternative is spending tokens to find out.
    if not 0 < len(out) < len(body):
        return body
    try:
        if not _lossless(json.loads(body), json.loads(out)):
            logger.warning("compaction: result dropped content, sending payload whole")
            return body
    except ValueError:
        # Either side unparseable means we cannot prove the fold is safe, and
        # unproven is the same as unsafe here.
        return body
    return out
