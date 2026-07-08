"""TikTok Research MCP server (stdio).

Tools:
  - search_tiktok_by_keyword   full-text TikTok search (metadata only)
  - search_tiktok_by_hashtag   posts for one or more hashtags (metadata only)
  - scrape_tiktok_url          deconstruct specific post/video URLs (metadata only)
  - get_tiktok_results         finish / re-fetch a run's dataset by id
  - fetch_tiktok_media         on-demand: images inline (base64) OR video → temp .mp4

Searches never download media — they return metadata + URLs so results stay
cheap and token-light. Fetch media only when you actually need to look at it.

Auth: reads APIFY_API_KEY (fallback APIFY_TOKEN) from the process environment.
Every keyword/hashtag/URL search is one billable Apify actor run — keep
results_per_page small while exploring.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from .apify_client import ApifyClient, ApifyAPIError
from .media import fetch_media_bytes, first_video_bytes, sniff_image_format
from .schema import ApifyRunStatus, ScrapedPost
from .shape import post_to_research_dict

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
logger = logging.getLogger("tiktok_research_mcp")

# The one actor that serves keyword search, hashtag search and single-URL scrape.
ACTOR = "clockworks/tiktok-scraper"

_DEAD = {
    ApifyRunStatus.FAILED,
    ApifyRunStatus.ABORTING,
    ApifyRunStatus.ABORTED,
    ApifyRunStatus.TIMING_OUT,
    ApifyRunStatus.TIMED_OUT,
}
_POLL_INTERVAL_S = 3.0

# Never fetch media during a search — only the dedicated fetch_tiktok_media tool does.
_NO_MEDIA: dict[str, Any] = {
    "shouldDownloadVideos": False,
    "shouldDownloadCovers": False,
    "shouldDownloadSlideshowImages": False,
    "shouldDownloadSubtitles": False,
    "shouldDownloadAvatars": False,
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


DEFAULT_RESULTS = _env_int("TIKTOK_MCP_DEFAULT_RESULTS", 20)
DEFAULT_MAX_WAIT_S = _env_float("TIKTOK_MCP_MAX_WAIT_S", 120.0)
MEDIA_DIR = Path(
    os.environ.get("TIKTOK_MCP_MEDIA_DIR", "").strip()
    or (Path(tempfile.gettempdir()) / "tiktok-research-mcp")
)


def _api_key() -> str:
    key = (os.environ.get("APIFY_API_KEY") or os.environ.get("APIFY_TOKEN") or "").strip()
    if not key:
        raise RuntimeError(
            "APIFY_API_KEY (or APIFY_TOKEN) is not set. Create a token at "
            "https://console.apify.com/account/integrations and pass it to the "
            "MCP server via its env config."
        )
    return key


def _as_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    return [str(x).strip() for x in value if str(x).strip()]


def _clean_hashtags(value: list[str] | str | None) -> list[str]:
    return [h.lstrip("#").strip() for h in _as_list(value) if h.lstrip("#").strip()]


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(int(n), hi))


async def _run(
    input_payload: dict[str, Any],
    *,
    results_limit: int,
    max_wait_s: float,
) -> tuple[ApifyRunStatus, str, str, list[ScrapedPost]]:
    """Start an actor run, poll to a terminal state (bounded by max_wait_s), and
    return (status, run_id, dataset_id, posts). posts is empty unless SUCCEEDED."""
    async with ApifyClient(_api_key()) as c:
        run = await c.start_run(ACTOR, input_payload)
        dataset_id = run.default_dataset_id
        waited = 0.0
        deadline = max(0.0, float(max_wait_s))
        while run.status not in ({ApifyRunStatus.SUCCEEDED} | _DEAD) and waited < deadline:
            await asyncio.sleep(_POLL_INTERVAL_S)
            waited += _POLL_INTERVAL_S
            run = await c.get_run(run.id)
            dataset_id = run.default_dataset_id or dataset_id
        posts: list[ScrapedPost] = []
        if run.status == ApifyRunStatus.SUCCEEDED:
            posts = await c.get_dataset_posts(dataset_id, limit=results_limit)
        return run.status, run.id, dataset_id, posts


def _envelope(
    status: ApifyRunStatus,
    run_id: str,
    dataset_id: str,
    posts: list[ScrapedPost],
    **extra: Any,
) -> dict:
    env: dict[str, Any] = {
        "status": status.value,
        "run_id": run_id,
        "dataset_id": dataset_id,
        "count": len(posts),
        "results": [post_to_research_dict(p) for p in posts],
    }
    env.update(extra)
    if status != ApifyRunStatus.SUCCEEDED:
        if status in _DEAD:
            env["note"] = f"Apify run ended without success (status={status.value})."
        else:
            env["note"] = (
                "Run still in progress at max_wait_s. Call "
                f"get_tiktok_results('{dataset_id}') in a bit to fetch the results."
            )
    return env


mcp = FastMCP("tiktok-research")


@mcp.tool()
async def search_tiktok_by_keyword(
    queries: list[str] | str,
    results_per_page: int = DEFAULT_RESULTS,
    max_wait_s: float = DEFAULT_MAX_WAIT_S,
    extra: dict | None = None,
) -> dict:
    """Search TikTok by keyword / free-text query for research & discovery.

    Returns compact post metadata (engagement stats, author, sound, hashtags,
    caption) plus media URLs — but NOT the media bytes. To view a cover image or
    the video, call fetch_tiktok_media afterwards with the URLs from the results.

    Args:
      queries: one keyword string, or a list of them (each is a separate search).
      results_per_page: posts to fetch per query (1–200). Each result costs Apify
        credits, so keep this modest while exploring. Default from env / 20.
      max_wait_s: how long to wait for the Apify run before returning a run_id to
        poll via get_tiktok_results. Default from env / 120s.
      extra: advanced Apify actor-input passthrough merged into the request, e.g.
        {"proxyConfiguration": {"countryCode": "US"}} for a region, or a date
        filter. Overrides the defaults for any key it sets.

    Each call is one billable Apify actor run (clockworks/tiktok-scraper).
    """
    qs = _as_list(queries)
    if not qs:
        raise ValueError("queries is required (a keyword string or list of them)")
    rpp = _clamp(results_per_page, 1, 200)
    payload: dict[str, Any] = {"searchQueries": qs, "resultsPerPage": rpp, **_NO_MEDIA}
    if extra:
        payload.update(extra)
    limit = _clamp(rpp * len(qs), 1, 1000)
    status, run_id, dataset_id, posts = await _run(payload, results_limit=limit, max_wait_s=max_wait_s)
    return _envelope(status, run_id, dataset_id, posts, query={"keywords": qs})


@mcp.tool()
async def search_tiktok_by_hashtag(
    hashtags: list[str] | str,
    results_per_page: int = DEFAULT_RESULTS,
    max_wait_s: float = DEFAULT_MAX_WAIT_S,
    extra: dict | None = None,
) -> dict:
    """Search TikTok by hashtag for research & discovery.

    Returns compact post metadata + media URLs (no media bytes). Fetch media via
    fetch_tiktok_media when you want to look at it.

    Args:
      hashtags: one hashtag or a list, with or without the leading '#'.
      results_per_page: posts per hashtag (1–200). Costs Apify credits.
      max_wait_s: run wait before returning a run_id to poll. Default env / 120s.
      extra: advanced Apify actor-input passthrough (e.g. proxy/region).

    Each call is one billable Apify actor run (clockworks/tiktok-scraper).
    """
    tags = _clean_hashtags(hashtags)
    if not tags:
        raise ValueError("hashtags is required (one tag or a list; '#' optional)")
    rpp = _clamp(results_per_page, 1, 200)
    payload: dict[str, Any] = {"hashtags": tags, "resultsPerPage": rpp, **_NO_MEDIA}
    if extra:
        payload.update(extra)
    limit = _clamp(rpp * len(tags), 1, 1000)
    status, run_id, dataset_id, posts = await _run(payload, results_limit=limit, max_wait_s=max_wait_s)
    return _envelope(status, run_id, dataset_id, posts, query={"hashtags": tags})


@mcp.tool()
async def scrape_tiktok_url(
    urls: list[str] | str,
    max_wait_s: float = DEFAULT_MAX_WAIT_S,
    extra: dict | None = None,
) -> dict:
    """Deconstruct one or more specific TikTok post/video URLs.

    Returns the same compact metadata + media URLs as the search tools (no media
    bytes). Use fetch_tiktok_media(kind="video", post_url=...) to download the
    actual clip for visual analysis.

    Args:
      urls: a TikTok post URL or a list of them.
      max_wait_s: run wait before returning a run_id to poll. Default env / 120s.
      extra: advanced Apify actor-input passthrough.

    Each call is one billable Apify actor run (clockworks/tiktok-scraper).
    """
    us = _as_list(urls)
    if not us:
        raise ValueError("urls is required (a TikTok post URL or list of them)")
    payload: dict[str, Any] = {"postURLs": us, "resultsPerPage": 1, **_NO_MEDIA}
    if extra:
        payload.update(extra)
    limit = _clamp(len(us), 1, 1000)
    status, run_id, dataset_id, posts = await _run(payload, results_limit=limit, max_wait_s=max_wait_s)
    return _envelope(status, run_id, dataset_id, posts, query={"urls": us})


@mcp.tool()
async def get_tiktok_results(dataset_id: str, limit: int = 200) -> dict:
    """Fetch (or re-fetch) the results of a finished Apify run by dataset id.

    Use this when a search returned status != SUCCEEDED (the run was still going
    when max_wait_s elapsed), or to page back through a prior run's results.

    Args:
      dataset_id: the dataset_id returned by a search / scrape tool.
      limit: max posts to return (1–1000).
    """
    async with ApifyClient(_api_key()) as c:
        posts = await c.get_dataset_posts(dataset_id, limit=_clamp(limit, 1, 1000))
    return {
        "dataset_id": dataset_id,
        "count": len(posts),
        "results": [post_to_research_dict(p) for p in posts],
    }


@mcp.tool()
async def fetch_tiktok_media(
    kind: str,
    image_urls: list[str] | None = None,
    post_url: str | None = None,
    max_images: int = 8,
    max_wait_s: float = DEFAULT_MAX_WAIT_S,
):
    """Download media on demand — the only tool that fetches bytes.

    Two modes:
      kind="images": pass image_urls (the cover_url / original_cover_url /
        slideshow_image_links from a search result). Returns the images inline so
        they can be viewed and analyzed directly. Capped at max_images.
      kind="video": pass post_url (a TikTok post URL). Runs a media-enabled
        scrape, downloads the .mp4 to a temp file, and returns its path + size
        (video is saved to disk, not returned inline). Hand the path to a
        video-understanding tool for visual analysis.

    Args:
      kind: "images" or "video".
      image_urls: image URLs to fetch (kind="images").
      post_url: TikTok post URL to download the clip for (kind="video").
      max_images: cap on inline images returned (kind="images").
      max_wait_s: run wait for the video scrape (kind="video").
    """
    k = (kind or "").strip().lower()

    if k == "images":
        urls = _as_list(image_urls)
        if not urls:
            raise ValueError('kind="images" requires image_urls')
        urls = urls[: _clamp(max_images, 1, 20)]
        token = _api_key()  # only used as a fallback for Apify-hosted URLs
        out: list[Any] = []
        ok = 0
        for url in urls:
            data = await asyncio.to_thread(fetch_media_bytes, url, token)
            if data:
                out.append(Image(data=data, format=sniff_image_format(data)))
                ok += 1
        out.append(f"Fetched {ok}/{len(urls)} image(s).")
        return out

    if k == "video":
        if not post_url or not post_url.strip():
            raise ValueError('kind="video" requires post_url')
        payload: dict[str, Any] = {
            "postURLs": [post_url.strip()],
            "resultsPerPage": 1,
            "shouldDownloadVideos": True,
            "shouldDownloadCovers": True,
            "shouldDownloadSlideshowImages": True,
        }
        status, run_id, dataset_id, posts = await _run(payload, results_limit=1, max_wait_s=max_wait_s)
        if status != ApifyRunStatus.SUCCEEDED or not posts:
            return {
                "status": status.value,
                "run_id": run_id,
                "dataset_id": dataset_id,
                "error": "video scrape did not complete successfully",
            }
        post = posts[0]
        data = await asyncio.to_thread(first_video_bytes, post.media_urls, _api_key())
        if not data:
            return {
                "status": "no_media",
                "note": "No downloadable .mp4 in the scrape (slideshow post, or media expired).",
                "post": post_to_research_dict(post),
            }
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(ch for ch in (post.id or "video") if ch.isalnum() or ch in "-_") or "video"
        path = MEDIA_DIR / f"{safe_id}.mp4"
        await asyncio.to_thread(path.write_bytes, data)
        return {
            "status": "ok",
            "path": str(path),
            "bytes": len(data),
            "content_type": "video/mp4",
            "post": post_to_research_dict(post),
        }

    raise ValueError('kind must be "images" or "video"')


def main() -> None:
    """Console-script / module entry point. Runs the stdio server."""
    mcp.run()


if __name__ == "__main__":
    main()
