"""Shared read path for the TikTok discovery feature.

Discovered posts are persisted as ``ContentAsset`` rows
(``asset_type='discovered_reference'``, ``source='apify'``) by
``routes/content.py::discover_save``. This module is the single query helper so
every consumer sees the same shape. Today the sole consumer is the Content
Planner's ``trend_scout`` sub-agent (the Content Studio agent no longer reads
discovery — planning owns it).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable
from uuid import UUID

from sqlmodel import Session, select

from db.session import get_engine
from models.content import AssetSource, AssetType, ContentAsset
from service import storage
from service.url_safety import host_in, is_public_http_url, safe_get_bytes

logger = logging.getLogger(__name__)

# Async callback the clone worker passes so each ingest stage surfaces as an SSE
# step. (step_id, status, message) — status in {"running", "ok", "error"}.
StepCb = Callable[..., Awaitable[None]]  # (step_id, status, message="", payload=None)


def query_discovered_references(
    db: Session,
    project_id: UUID,
    *,
    min_plays: int = 10000,
    limit: int = 30,
) -> list[dict]:
    """Return saved high-performing TikTok posts for a project, newest first,
    filtered to ``play_count >= min_plays``. Shape mirrors what the agent cites
    (``asset_id`` + ``tiktok_url`` for evidence, plus engagement + metadata).
    """
    rows = db.exec(
        select(ContentAsset)
        .where(
            ContentAsset.project_id == project_id,
            ContentAsset.asset_type == AssetType.DISCOVERED_REFERENCE,
        )
        .order_by(ContentAsset.created_at.desc())  # type: ignore[union-attr]
        .limit(200)  # over-fetch; filter in Python by min_plays
    ).all()

    items: list[dict] = []
    for r in rows:
        p = (r.params or {}).get("post") or {}
        if (p.get("play_count") or 0) < min_plays:
            continue
        items.append({
            "asset_id":      str(r.id),
            "tiktok_url":    r.url,
            "play_count":    p.get("play_count"),
            "digg_count":    p.get("digg_count"),
            "comment_count": p.get("comment_count"),
            "share_count":   p.get("share_count"),
            "collect_count": p.get("collect_count"),
            "hashtags":      p.get("hashtags") or [],
            "music":         (p.get("music_meta") or {}).get("music_name"),
            "author":        (p.get("author_meta") or {}).get("name"),
            "is_slideshow":  p.get("is_slideshow"),
            "text":          (p.get("text") or "")[:280],
            "created_at":    p.get("create_time_iso"),
        })
        if len(items) >= limit:
            break
    return items


def saved_reference_urls(db: Session, project_id: UUID) -> set[str]:
    """Every TikTok URL the project has saved as a discovered reference. Used to
    validate plan ``evidence`` so a citation can't be fabricated by the model —
    receipts are true by construction."""
    rows = db.exec(
        select(ContentAsset).where(
            ContentAsset.project_id == project_id,
            ContentAsset.asset_type == AssetType.DISCOVERED_REFERENCE,
        )
    ).all()
    return {r.url for r in rows if r.url}


# ---------------------------------------------------------------------------
# Media capture — runs as a FastAPI BackgroundTask after a post is saved, and
# via recapture_missing_media() as a backfill for tasks lost to a restart.
# ---------------------------------------------------------------------------

_IMG_CONTENT_TYPE = "image/jpeg"
_DOWNLOAD_ATTEMPTS = 2


def _download_to_bucket(src_url: str, key: str) -> str:
    """Fetch bytes from a TikTok CDN or Apify-hosted URL and store them in our
    bucket. Retries once on a transient miss. When the scrape requests
    shouldDownloadCovers/Slideshow the cover + slides live in Apify's key-value
    store, whose record URLs are token-gated (a plain GET 403s) — so on failure
    retry with the API token appended, but ONLY when the host is genuinely Apify
    (never append the token to a TikTok/other host: that would leak it). Returns
    the stored URL, or "" on failure."""
    if not src_url:
        return ""
    for attempt in range(_DOWNLOAD_ATTEMPTS):
        data = storage.get_bytes(src_url)
        if data:
            return storage.put_image(key, data, _IMG_CONTENT_TYPE)
        if attempt + 1 < _DOWNLOAD_ATTEMPTS:
            time.sleep(0.4)
    # Apify key-value-store records need the token (mirrors _fetch_reference_video_bytes).
    if host_in(src_url, _APIFY_HOSTS) and is_public_http_url(src_url):
        from config import get_configs

        token = (get_configs().apify_api_key or "").strip()
        if token:
            sep = "&" if "?" in src_url else "?"
            data = storage.get_bytes(f"{src_url}{sep}token={token}")
            if data:
                return storage.put_image(key, data, _IMG_CONTENT_TYPE)
    return ""


def capture_reference_media(asset_id: UUID, post: dict) -> None:
    """Persist a saved post's cover + slideshow images into our bucket, then
    patch the asset's ``params.media`` with a STATUS so the outcome is never
    silent:

      - ``ok``      — captured at least the cover or a slide
      - ``failed``  — had source URLs but every download failed (e.g. expired)
      - ``empty``   — nothing to capture (video with no cover/slides)

    Why: TikTok's CDN URLs are signed and expire within hours, so a saved
    reference loses its imagery unless we download the bytes promptly. Runs as a
    BackgroundTask on save and as a backfill via recapture_missing_media. Always
    best-effort — failures are logged, not raised. Video + subtitles need a
    re-scrape with download flags (Apify-metered) and are deferred to clone-time.
    """
    try:
        vm = post.get("video_meta") or {}
        slides_src = list(post.get("slideshow_image_links") or [])
        cover_src = vm.get("cover_url") or vm.get("original_cover_url") or (slides_src[0] if slides_src else "")
        had_sources = bool(cover_src or slides_src)

        media: dict = {
            "cover": "",
            "slides": [],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        cover_url = _download_to_bucket(cover_src, f"discover/{asset_id}/cover.jpg")
        if cover_url:
            media["cover"] = cover_url
        for i, s in enumerate(slides_src):
            stored = _download_to_bucket(s, f"discover/{asset_id}/slide-{i:02d}.jpg")
            if stored:
                media["slides"].append(stored)

        captured = bool(media["cover"] or media["slides"])
        media["status"] = "ok" if captured else ("failed" if had_sources else "empty")

        # Always persist the marker (even on failure) so a lost/failed capture is
        # visible and recoverable, never a silent gap that breaks clone-time.
        engine = get_engine()
        if engine is None:
            return
        with Session(engine) as db:
            asset = db.get(ContentAsset, asset_id)
            if asset is None:
                return
            params = dict(asset.params or {})
            params["media"] = media
            asset.params = params  # reassign so SQLAlchemy detects the JSONB change
            db.add(asset)
            db.commit()
        logger.info(
            "discover: media %s for asset=%s (cover=%s, slides=%d)",
            media["status"], asset_id, bool(media["cover"]), len(media["slides"]),
        )
    except Exception:
        logger.exception("discover: capture_reference_media failed for asset=%s", asset_id)


def recapture_missing_media(project_id: UUID, *, limit: int = 50) -> dict:
    """Backfill: re-attempt media capture for saved discoveries whose capture
    never ran (task lost to a restart → no ``params.media``) or failed.

    The TikTok CDN URLs expire within hours, so this only recovers recently
    saved posts; older ones re-mark ``failed`` so clone-time knows to re-scrape.
    Idempotent and safe to run repeatedly (cron-able later). Returns counts.
    """
    engine = get_engine()
    if engine is None:
        return {"scanned": 0, "recaptured": 0, "still_missing": 0, "pending": 0}

    with Session(engine) as db:
        rows = db.exec(
            select(ContentAsset).where(
                ContentAsset.project_id == project_id,
                ContentAsset.asset_type == AssetType.DISCOVERED_REFERENCE,
            ).order_by(ContentAsset.created_at.desc())  # type: ignore[union-attr]
        ).all()
        targets: list[tuple[UUID, dict]] = []
        for r in rows:
            params = r.params or {}
            media = params.get("media") or {}
            if not media or media.get("status") == "failed":
                targets.append((r.id, params.get("post") or {}))

    pending = max(0, len(targets) - limit)
    targets = targets[:limit]
    for asset_id, post in targets:
        capture_reference_media(asset_id, post)

    recaptured = still_missing = 0
    if targets:
        with Session(engine) as db:
            for asset_id, _ in targets:
                a = db.get(ContentAsset, asset_id)
                status = ((a.params or {}).get("media") or {}).get("status") if a else None
                if status == "ok":
                    recaptured += 1
                else:
                    still_missing += 1
    return {
        "scanned": len(targets),
        "recaptured": recaptured,
        "still_missing": still_missing,
        "pending": pending,
    }


# ---------------------------------------------------------------------------
# Clone-time intelligence: read "why it worked" from the metrics, and the
# deferred single-URL ingest the clone_post worker runs on first Draft-now.
# ---------------------------------------------------------------------------

# Algorithm signal hierarchy (2026): watch-time/completion (INVISIBLE in public
# counts) > comment depth ≈ send-to-DM shares > saves > likes. We can only read the
# public counts, so we rank by rate × weight and name a crude lever PRIOR — the
# Gemini "why it worked" decode (build_deconstruction_prompt Phase B) is the real
# diagnosis and overrides this when they conflict. Comments were raised from the old
# 1.5 to parity with saves (2026: comments now outrank likes; shares-to-DM are the
# loudest public virality signal). Mirrored on the frontend in
# app/src/lib/contentMetrics.js::diagnoseReference — keep the two in sync.
_LEVER_WEIGHTS = {"shares": 3.0, "saves": 2.5, "comments": 2.5, "likes": 1.0}
_LEVER_SUMMARY = {
    "saves":    "Won on SAVES (utility) — clone a genuinely save-worthy how-to / list / framework in your niche and add an explicit \"save this\" CTA.",
    "shares":   "Won on SHARES (identity/emotion) — clone the relatable or aspirational angle and the \"send this to a friend\" trigger.",
    "comments": "Won on COMMENTS (debate/community) — clone the opinion or open-question hook that makes people reply.",
    "likes":    "Likes are the weakest signal — copy the hook for reach, but build a stronger save/share payoff than the original.",
}


def diagnose_reference(post: dict) -> dict:
    """Compute engagement ratios and name the single dominant lever a reference
    won on, so the clone agent copies *that* (not the surface). `post` is a
    ScrapedPost dict. A save_rate >2% is a strong FYP signal."""
    post = post or {}
    views    = int(post.get("play_count") or 0)
    likes    = int(post.get("digg_count") or 0)
    comments = int(post.get("comment_count") or 0)
    shares   = int(post.get("share_count") or 0)
    saves    = int(post.get("collect_count") or 0)

    def _rate(n: int) -> float | None:
        return round(n / views, 5) if views else None

    rates = {
        "saves":    _rate(saves),
        "shares":   _rate(shares),
        "comments": _rate(comments),
        "likes":    _rate(likes),
    }
    scored = [(k, v * _LEVER_WEIGHTS[k]) for k, v in rates.items() if v is not None]
    lever = max(scored, key=lambda kv: kv[1])[0] if scored else None
    return {
        "views": views, "likes": likes, "comments": comments,
        "shares": shares, "saves": saves,
        "save_rate": rates["saves"], "share_rate": rates["shares"],
        "comment_rate": rates["comments"], "like_rate": rates["likes"],
        "lever": lever,
        "summary": _LEVER_SUMMARY.get(lever or "", ""),
        "strong_save_signal": bool(rates["saves"] and rates["saves"] >= 0.02),
        "is_slideshow": bool(post.get("is_slideshow")),
        # Confidence is low when we lack saves (e.g. PostBridge exposes only 4
        # public counts) — the agent should then infer the lever qualitatively.
        "confidence": "high" if (views and saves) else "low",
    }


# The Phase-B decode emits a "## WHY IT WORKED" prose section + a trailing fenced
# ```json block. These slice them back out: the prose feeds the "Decoding why it
# worked" UI panel; the json is the structured storyboard (hook_type, structure_pct,
# loops, beat_map, search_keywords, …). Both are best-effort — a Phase-A-only
# re-watch has neither, and callers fall back to the deterministic diagnostic.
_WHY_HEADER_RE = re.compile(r"^#{1,6}\s*WHY IT WORKED.*$", re.IGNORECASE | re.MULTILINE)
_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def split_why_section(analysis: str) -> str:
    """Slice the '## WHY IT WORKED' growth decode out of a Phase-B deconstruction,
    stripping the trailing json fence. '' when absent (Phase-A-only)."""
    if not analysis:
        return ""
    m = _WHY_HEADER_RE.search(analysis)
    if not m:
        return ""
    why = analysis[m.start():]
    fence = why.find("```json")
    if fence != -1:
        why = why[:fence]
    return why.strip()


def parse_analysis_struct(analysis: str) -> dict:
    """Best-effort parse of the trailing fenced ```json block (hook_type,
    structure_pct, loops, beat_map, search_keywords, why_it_worked, copy_this,
    beat_this, …). {} on absence/malformed json — the pipeline never depends on it."""
    if not analysis:
        return {}
    m = _JSON_FENCE_RE.search(analysis)
    if not m:
        return {}
    try:
        val = json.loads(m.group(1))
        return val if isinstance(val, dict) else {}
    except (ValueError, TypeError):
        return {}


async def _scrape_single_post(url: str, *, max_wait_s: float = 120.0) -> dict | None:
    """Run the single-URL TikTok scrape (Apify clockworks/tiktok-scraper) with
    media-download flags and poll to completion. Returns one ScrapedPost dict or
    None. This is the paid step — the worker only calls it when nothing is cached."""
    from config import get_configs
    from service.apify import ApifyAPIError, ApifyClient
    from service.apify.client import get_default_actor_ids
    from service.apify.schema import ApifyRunStatus

    cfg = get_configs()
    if not cfg.apify_api_key:
        return None
    actor_id = get_default_actor_ids()["post_by_hashtag"]  # clockworks/tiktok-scraper
    payload = {
        "postURLs": [url],
        "resultsPerPage": 1,
        "shouldDownloadCovers": True,
        "shouldDownloadSlideshowImages": True,
        # Download the .mp4 so a VIDEO clone can be deconstructed by Gemini video
        # understanding (the actor stores it + returns mediaUrls). No-op cost for
        # slideshows (no video to download); this is the clone-only single scrape.
        "shouldDownloadVideos": True,
    }
    dead = {
        ApifyRunStatus.FAILED, ApifyRunStatus.ABORTING, ApifyRunStatus.ABORTED,
        ApifyRunStatus.TIMING_OUT, ApifyRunStatus.TIMED_OUT,
    }
    try:
        async with ApifyClient(cfg.apify_api_key) as c:
            run = await c.start_run(actor_id, payload)
            dataset_id = run.default_dataset_id
            waited = 0.0
            while run.status not in ({ApifyRunStatus.SUCCEEDED} | dead) and waited < max_wait_s:
                await asyncio.sleep(3.0)
                waited += 3.0
                run = await c.get_run(run.id)
                dataset_id = run.default_dataset_id or dataset_id
            if run.status != ApifyRunStatus.SUCCEEDED:
                logger.warning("clone ingest: run %s ended status=%s", run.id, run.status)
                return None
            posts = await c.get_dataset_posts(dataset_id, limit=1)
            return posts[0].model_dump(mode="json") if posts else None
    except (ApifyAPIError, ValueError):
        logger.exception("clone ingest: scrape failed for %s", url)
        return None


def _reference_media(asset: ContentAsset | None) -> dict:
    return dict(((asset.params or {}).get("media") or {})) if asset else {}


# Apify CDN / key-value-store hosts — the ONLY hosts we'll append the Apify token
# to (exact match, never a substring: "https://evil.com/?x=api.apify.com" must
# NOT leak the token).
_APIFY_HOSTS = {"api.apify.com", "storage.apify.com"}

# Reference clips are a few MB — well over the 20s image-fetch default.
_VIDEO_FETCH_TIMEOUT_SECS = 60.0


def _fetch_reference_video_bytes(post: dict) -> bytes | None:
    """Fetch the reference .mp4 bytes from the Apify-hosted ``mediaUrls`` (set
    when the scrape requested shouldDownloadVideos). Apify key-value-store record
    URLs may need the API token, so retry with it appended — but ONLY when the host
    is genuinely Apify (else we'd leak the token). The URL itself must be a public
    http(s) host (SSRF guard) since it comes from a third-party API response.
    Returns None if there is no video URL or every fetch fails (caller falls back
    to cover+metadata)."""
    src = (post.get("media_urls") or [""])[0]
    if not src or not is_public_http_url(src):
        return None
    # Videos can be a few MB — give the fetch more headroom than the 20s image default.
    data = safe_get_bytes(src, timeout=_VIDEO_FETCH_TIMEOUT_SECS)  # untrusted → SSRF-guarded
    if not data and host_in(src, _APIFY_HOSTS):
        from config import get_configs

        token = (get_configs().apify_api_key or "").strip()
        if token:
            sep = "&" if "?" in src else "?"
            data = safe_get_bytes(f"{src}{sep}token={token}", timeout=_VIDEO_FETCH_TIMEOUT_SECS)
    return data or None


async def _run_understanding(**understand_kwargs) -> str:
    """Resolve the Gemini key, build the client, and run understand_video with the
    given knobs (data|youtube_url, fps, start/end_offset, media_resolution, model).
    Returns "" on any failure (no key / SDK error) so callers fall back to cover +
    metadata. ``None`` knobs are dropped so understand_video's defaults apply."""
    from config import get_configs
    from service.gemini.video import GeminiVideoClient

    api_key = (get_configs().gemini_api_key or "").strip()
    if not api_key:
        return ""
    kwargs = {k: v for k, v in understand_kwargs.items() if v is not None}
    try:
        return await GeminiVideoClient(api_key).understand_video(**kwargs)
    except Exception:
        logger.exception("clone ingest: video understanding failed")
        return ""


async def analyze_video_bytes(data: bytes, **knobs) -> str:
    """Deconstruct clip bytes → director-grade structured analysis (beats,
    transformation arc, on-screen text, audio). **knobs forwards the documented
    levers (fps, start_offset, end_offset, media_resolution, model)."""
    if not data:
        return ""
    return await _run_understanding(data=data, mime_type="video/mp4", **knobs)


async def analyze_youtube_video(youtube_url: str, **knobs) -> str:
    """Deconstruct a public YouTube URL (passed to Gemini as fileData — no local
    download). For long-form sources; **knobs forwards the documented levers."""
    if not youtube_url:
        return ""
    return await _run_understanding(youtube_url=youtube_url, **knobs)


async def understand_reference_video(post: dict, **knobs) -> str:
    """Fetch the reference .mp4 (Apify-hosted) and deconstruct it. The single
    analysis entry point the understand_video tool uses when it only has the
    scraped post; clone ingest fetches the bytes once and calls analyze_video_bytes
    directly to avoid a double download. **knobs forwards the documented levers."""
    data = await asyncio.to_thread(_fetch_reference_video_bytes, post)
    return await analyze_video_bytes(data, **knobs) if data else ""


def _reference_preview(post: dict) -> dict:
    """Compact reference card for the 'Scraping' step's detail panel — the
    same shape the paste-a-URL dialog shows: cover thumbnail + handle + caption
    + the public engagement counts the clone is modeling. The TikTok cover URL
    is used as-is (it loads cross-origin, like the oembed thumbnail does)."""
    vm = post.get("video_meta") or {}
    am = post.get("author_meta") or {}
    return {
        "thumbnail": vm.get("cover_url") or vm.get("original_cover_url") or "",
        "author":    am.get("nick_name") or am.get("name") or "",
        "caption":   (post.get("text") or "")[:280],
        "post_type": "video" if post.get("is_slideshow") is False else "slideshow",
        "views":     post.get("play_count"),
        "likes":     post.get("digg_count"),
        "comments":  post.get("comment_count"),
        "shares":    post.get("share_count"),
        "saves":     post.get("collect_count"),
    }


async def ingest_reference(project_id: UUID, clone_source: dict, *, on_step: StepCb | None = None) -> dict:
    """Resolve a `clone_source` pointer into a full reference card:
    ``{tiktok_url, asset_id, scraped_post, media, diagnostic, error}``.

    The expensive Apify scrape runs only when nothing is cached:
      - cached ``clone_source.scraped_post`` → reuse (a re-draft never re-charges);
      - kind == "reference" → reuse the saved ``discovered_reference`` post;
      - kind == "url" → scrape once, persist a ``discovered_reference`` (joins the
        library), then capture media.
    Media is captured only when missing. Coarse stages surface via ``on_step``.
    Sync DB / network work runs in threads so the event loop stays responsive."""
    async def _step(sid: str, status: str, msg: str = "", payload: dict | None = None) -> None:
        if on_step is not None:
            await on_step(sid, status, msg, payload)

    kind = (clone_source or {}).get("kind") or "url"
    url = (clone_source or {}).get("url") or ""
    ref_asset_id = (clone_source or {}).get("reference_asset_id")
    cached_post = (clone_source or {}).get("scraped_post")
    engine = get_engine()

    await _step("resolving", "running", "Resolving the reference…")
    asset_id: UUID | None = None
    post: dict | None = None

    if cached_post:
        post = cached_post
        await _step("resolving", "ok", "Using the cached reference.")
    elif kind == "reference" and ref_asset_id and engine is not None:
        def _load():
            with Session(engine) as db:
                a = db.get(ContentAsset, UUID(str(ref_asset_id)))
                return (a.id, a.url, (a.params or {}).get("post")) if a else (None, "", None)
        asset_id, url, post = await asyncio.to_thread(_load)
        await _step("resolving", "ok", "Loaded saved reference.")

    if post is None and url:
        # Close the resolving step before scraping — the cached / saved-asset
        # branches above already do, but the freshly-pasted-URL path didn't, so
        # "Resolving the reference" span as a spinner for the whole run.
        await _step("resolving", "ok", "Resolved the link.")
        await _step("scraping", "running", "Scraping the TikTok (metadata + media)…")
        post = await _scrape_single_post(url)
        if post is None:
            await _step("scraping", "error", "Couldn't fetch this TikTok.")
            return {"error": "scrape_failed", "tiktok_url": url, "scraped_post": None,
                    "media": {}, "diagnostic": {}, "asset_id": None}
        url = post.get("web_video_url") or url
        # Persist as a discovered_reference so URL-pasted posts join the library.
        if engine is not None:
            def _save():
                with Session(engine) as db:
                    a = ContentAsset(
                        project_id=project_id,
                        asset_type=AssetType.DISCOVERED_REFERENCE,
                        source=AssetSource.APIFY,
                        url=post.get("web_video_url") or url,
                        filename=f"tiktok-{post.get('id')}",
                        mime_type="application/json",
                        params={"post": post, "saved_at": datetime.now(timezone.utc).isoformat()},
                    )
                    db.add(a)
                    db.commit()
                    db.refresh(a)
                    return a.id
            asset_id = await asyncio.to_thread(_save)
        await _step("scraping", "ok", "Fetched the post.", payload=_reference_preview(post))

    if post is None:
        return {"error": "no_source", "tiktok_url": url, "scraped_post": None,
                "media": {}, "diagnostic": {}, "asset_id": None}

    # Capture media (cover + slides) into our bucket if it isn't there yet.
    media: dict = {}
    if asset_id is not None and engine is not None:
        # Emit "running" unconditionally (even on a cached hit) so the UI always
        # gets a STEP_STARTED to attach the finished count to.
        await _step("media", "running", "Saving cover & slide images…")

        def _existing_media():
            with Session(engine) as db:
                return _reference_media(db.get(ContentAsset, asset_id))
        media = await asyncio.to_thread(_existing_media)
        if (media.get("status") or "") != "ok":
            await asyncio.to_thread(capture_reference_media, asset_id, post)
            media = await asyncio.to_thread(_existing_media)
        await _step("media", "ok", "Media captured.", payload={
            "cover":  bool(media.get("cover")),
            "slides": len(media.get("slides") or []),
            "video":  bool(media.get("video")),
        })

    # The deterministic lever PRIOR — computed up-front so it can be fed INTO the
    # video decode (the watch + "why it worked" are now ONE merged Gemini pass) and
    # surfaced as the UI lever badge. The Gemini decode overrides it qualitatively.
    diagnostic = diagnose_reference(post)

    # For a VIDEO reference, deconstruct the clip itself with Gemini video
    # understanding — the agent can't watch an mp4, so this is its eyes (Higgsfield's
    # analyser missed the before→after transformation + on-screen text). Capture the
    # mp4 into our bucket first (a stable URL — Apify CDN links expire), then analyse
    # the SAME bytes in ONE pass: the enriched craft read PLUS a Phase-B "why it
    # worked" growth decode grounded in THIS post's metrics + creator size (reasoning
    # over the actual frames beats a second LLM call over a text summary). Best-effort:
    # on any failure the agent falls back to cover + metadata + the deterministic lever.
    video_analysis = ""
    why_text = ""
    analysis_struct: dict = {}
    if post.get("is_slideshow") is False:
        await _step("watching", "running", "Watching the video frame by frame…")
        data = await asyncio.to_thread(_fetch_reference_video_bytes, post)
        if data:
            if asset_id is not None:
                stored = await asyncio.to_thread(
                    storage.put_image, f"discover/{asset_id}/video.mp4", data, "video/mp4"
                )
                if stored:
                    media = {**media, "video": stored}
            from service.gemini.video import build_deconstruction_prompt

            prompt = build_deconstruction_prompt(
                diagnostic=diagnostic, author=post.get("author_meta"),
            )
            video_analysis = await analyze_video_bytes(data, prompt=prompt)
        why_text = split_why_section(video_analysis)
        analysis_struct = parse_analysis_struct(video_analysis)
        await _step(
            "watching", "ok" if video_analysis else "error",
            "Deconstructed the video." if video_analysis else "Couldn't read the clip — using the cover.",
            payload={"analyzed": bool(video_analysis), "analysis": video_analysis[:4000]},
        )
        # Persist onto the discovered_reference asset so the library entry carries
        # the analysis (a re-clone reuses it; mirrors params.media for cover/slides).
        if asset_id is not None and engine is not None and (video_analysis or media.get("video")):
            _vid_url, _vid_analysis, _vid_struct = media.get("video") or "", video_analysis, analysis_struct

            def _persist_video_meta() -> None:
                with Session(engine) as db:
                    a = db.get(ContentAsset, asset_id)
                    if a is None:
                        return
                    params = dict(a.params or {})
                    m = dict(params.get("media") or {})
                    if _vid_url:
                        m["video"] = _vid_url
                    if _vid_analysis:
                        m["video_analysis"] = _vid_analysis
                    if _vid_struct:
                        m["video_analysis_struct"] = _vid_struct
                    params["media"] = m
                    a.params = params  # reassign so SQLAlchemy detects the JSONB change
                    db.add(a)
                    db.commit()

            # Best-effort mirror — the analysis is already in the return dict and cached
            # onto clone_source by run_clone, so a transient DB error here must NOT abort
            # the whole clone (matches capture_reference_media's fail-soft contract).
            try:
                await asyncio.to_thread(_persist_video_meta)
            except Exception:
                logger.warning("clone ingest: couldn't mirror video analysis onto the reference asset", exc_info=True)

    # "Decoding why it worked": prefer the Gemini growth decode (video refs); fall
    # back to the deterministic lever summary (slideshows, or video analysis failed).
    await _step("analyzing", "running", "Decoding why it worked…")
    why_summary = why_text or diagnostic.get("summary", "")
    await _step("analyzing", "ok", why_summary, payload={
        **{k: diagnostic.get(k) for k in ("lever", "summary", "views", "likes", "comments", "shares", "saves")},
        "why_it_worked": why_text or None,
        "struct": analysis_struct or None,
    })

    return {
        "tiktok_url": url,
        "asset_id": str(asset_id) if asset_id else None,
        "scraped_post": post,
        "media": media,
        "diagnostic": diagnostic,
        "video_analysis": video_analysis,
        "video_analysis_struct": analysis_struct,
        "why_it_worked": why_text,
        "error": None,
    }
