"""What a Duct user may ask Apify to run on Duct's account.

``/content/discover/start`` used to pass the browser's ``actor_id`` and
``input_payload`` straight to Apify. The key is Duct's, so any signed-in user
(a guest is a user) could run any actor in the Apify store, with any input,
on Duct's bill. The Discover page only ever sends two actors with a handful
of fields; this is that, written down, and nothing else gets through.
"""

from __future__ import annotations

from typing import Any

from service.apify.client import get_default_actor_ids

#: A page of results is what Discover shows; more is a bill, not a feature.
MAX_RESULTS_PER_PAGE = 50
MAX_HASHTAGS = 10
MAX_TEXT = 100

_POST_BY_HASHTAG = get_default_actor_ids()["post_by_hashtag"]
_TREND_FEED = get_default_actor_ids()["trend_feed"]

# Download switches cost Apify compute and storage per post; Discover never
# needs the files, so they are pinned off whatever the caller sent.
_NO_DOWNLOADS = {
    "shouldDownloadVideos": False,
    "shouldDownloadCovers": False,
    "shouldDownloadSubtitles": False,
}


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError(f"invalid {field}")
    return value.strip()


def _results(payload: dict[str, Any]) -> int:
    value = payload.get("resultsPerPage", 30)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("invalid resultsPerPage")
    return min(value, MAX_RESULTS_PER_PAGE)


def discover_run_input(actor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """The input Duct will actually send for ``actor_id``, or ValueError.

    Rebuilt from known fields rather than filtered, so a field Apify adds
    later cannot ride along unreviewed.
    """
    if actor_id == _POST_BY_HASHTAG:
        tags = payload.get("hashtags")
        if not isinstance(tags, list) or not 1 <= len(tags) <= MAX_HASHTAGS:
            raise ValueError(f"hashtags must be a list of 1 to {MAX_HASHTAGS}")
        return {
            "hashtags": [_text(tag, "hashtag") for tag in tags],
            "resultsPerPage": _results(payload),
            **_NO_DOWNLOADS,
        }
    if actor_id == _TREND_FEED:
        run_input: dict[str, Any] = {"type": "TREND", "resultsPerPage": _results(payload)}
        if payload.get("region"):
            run_input["region"] = _text(payload["region"], "region")
        return run_input
    raise ValueError(f"actor not available: {actor_id!r}")
