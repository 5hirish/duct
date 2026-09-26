"""Saved TikTok references: ingest one post, and keep its pictures.

A reference is a ``ContentAsset`` row (``discovered_reference``, source
``apify``) whose ``params["post"]`` is the scraped post. The post's cover and
slide URLs are TikTok CDN links with a signed expiry, so a reference that only
stores them loses its pictures within days. Saving therefore has two steps:

1. ``ingest_reference`` writes the row. Fast, no network, one per post.
2. ``capture_reference_media`` copies the cover and slides into project
   storage and records the outcome in ``params["media"]``. Slow and network
   bound, so the caller decides where it runs — after the response on a save,
   in a worker for a clone.

Both are plain functions over a session and an HTTP client, so anything that
has a ``ScrapedPost`` — the Discover save today, a clone-from-URL scrape next —
ingests it the same way. A capture that never ran (a restart ate the background
task) or failed is found again by ``references_missing_media``.

No table of its own: the media record rides on the asset row it describes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlmodel import Session, select

from config import get_configs
from db.session import get_engine
from models.content import ContentAsset
from service import storage
from service.apify.schema import ScrapedPost
from service.url_safety import FetchRefused, fetch_allowlisted
from utils.dates import now_iso

logger = logging.getLogger(__name__)

REFERENCE_ASSET_TYPE = "discovered_reference"
REFERENCE_SOURCE = "apify"


class MediaStatus(StrEnum):
    """``params["media"]["status"]`` on a reference."""

    OK = "ok"            # every source copied
    PARTIAL = "partial"  # some copied; retried until MAX_CAPTURE_ATTEMPTS
    FAILED = "failed"    # had sources, copied none; retried the same way
    EMPTY = "empty"      # the post named no image at all; nothing to retry


# Where a scraped post's images live. TikTok splits its image CDN by region
# (tiktokcdn.com, -us, -eu) and serves some covers from ByteDance's
# ibyteimg.com; a run that downloads covers or slides itself hands back an
# Apify key-value-store record on its API host. Anything else is refused and
# logged with its host, so a CDN TikTok adds later is one line here.
MEDIA_DOMAINS = frozenset({
    "tiktokcdn.com",
    "tiktokcdn-us.com",
    "tiktokcdn-eu.com",
    "ibyteimg.com",
    "api.apify.com",
})

# What we will store, and the extension it is stored under. SVG is absent on
# purpose: served back from our own origin it is a document that runs script.
_IMAGE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
}

# A TikTok slide is a phone-sized JPEG of a few hundred KB; ten times that
# is not a slide.
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# TikTok's photo mode allows 35 images; a list longer than that did not come
# from TikTok.
MAX_SLIDES = 35

# A failed or partial capture is retried this many times in total. The URLs
# expire, so an attempt that fails for good tends to keep failing, and without
# a ceiling every backfill would fetch the same dead links again.
MAX_CAPTURE_ATTEMPTS = 3

# How many references one backfill request copies. Newest first, because
# their URLs are the likeliest to still be signed.
BACKFILL_BATCH = 25

_FETCH_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
_USER_AGENT = "DuctContentAgent/1.0 (+https://getduct.ai)"

# Key-value-store records sit behind the account token (a bare GET is a 403).
# It is sent as a header, not the ``?token=`` the docs also accept, so it never
# lands in a URL that httpx logs; and only to this host and path, so a record
# URL is the one thing a caller can make us present it to.
_APIFY_API_HOST = "api.apify.com"
_APIFY_RECORD_PATH = "/v2/key-value-stores/"

OpenDb = Callable[[], Session]


def _open_db() -> Session:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    return Session(engine)


def _new_media_client() -> httpx.Client:
    return httpx.Client(timeout=_FETCH_TIMEOUT, headers={"User-Agent": _USER_AGENT})


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def ingest_reference(
    db: Session,
    project_id: UUID,
    post: ScrapedPost,
    *,
    provenance: Mapping[str, Any] | None = None,
) -> ContentAsset:
    """Save *post* as one of the project's references and return the row.

    One row per TikTok post per project: saving a post again refreshes its
    counts and URLs rather than adding a duplicate. A capture that already
    succeeded is kept; any other outcome is cleared, because the post just
    arrived with freshly signed URLs and deserves a clean set of attempts.

    ``provenance`` is whatever the caller wants remembered about where the
    post came from (the actor, run and search for Discover). Media is not
    fetched here — follow with ``capture_reference_media`` when
    ``needs_media`` says so.
    """
    filename = f"tiktok-{post.id}"
    dumped = post.model_dump(mode="json")
    asset = db.exec(
        select(ContentAsset).where(
            ContentAsset.project_id == project_id,
            ContentAsset.asset_type == REFERENCE_ASSET_TYPE,
            ContentAsset.filename == filename,
        )
    ).first()

    if asset is None:
        asset = ContentAsset(
            project_id=project_id,
            asset_type=REFERENCE_ASSET_TYPE,
            source=REFERENCE_SOURCE,
            url=post.web_video_url or f"tiktok://{post.id}",
            filename=filename,
            mime_type="application/json",
            params={**dict(provenance or {}), "post": dumped, "saved_at": now_iso()},
        )
    else:
        params = {**(asset.params or {}), **dict(provenance or {}), "post": dumped}
        if (params.get("media") or {}).get("status") != MediaStatus.OK:
            params.pop("media", None)
        asset.params = params  # a new dict, so SQLAlchemy sees the JSON change
        asset.url = post.web_video_url or asset.url
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def needs_media(params: Mapping[str, Any] | None) -> bool:
    """Whether a reference with these params should be (re)captured."""
    media = (params or {}).get("media")
    if not media:
        return True
    return (
        media.get("status") in (MediaStatus.FAILED, MediaStatus.PARTIAL)
        and int(media.get("attempts") or 0) < MAX_CAPTURE_ATTEMPTS
    )


def references_missing_media(
    db: Session, project_id: UUID, *, limit: int = BACKFILL_BATCH
) -> list[UUID]:
    """Ids of the project's references whose media should be captured, newest first."""
    rows = db.exec(
        select(ContentAsset)
        .where(
            ContentAsset.project_id == project_id,
            ContentAsset.asset_type == REFERENCE_ASSET_TYPE,
        )
        .order_by(ContentAsset.created_at.desc())  # type: ignore[union-attr]
    ).all()
    return [r.id for r in rows if needs_media(r.params)][:limit]


# ---------------------------------------------------------------------------
# Media capture
# ---------------------------------------------------------------------------


def _media_sources(post: Mapping[str, Any]) -> tuple[str, list[str]]:
    video = post.get("video_meta") or {}
    cover = video.get("cover_url") or video.get("original_cover_url") or ""
    slides = [u for u in (post.get("slideshow_image_links") or []) if isinstance(u, str) and u]
    return cover, slides[:MAX_SLIDES]


def _auth_headers(url: str) -> dict[str, str]:
    parts = urlsplit(url)
    if (parts.hostname or "").lower() != _APIFY_API_HOST or not parts.path.startswith(_APIFY_RECORD_PATH):
        return {}
    token = (get_configs().apify_api_key or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _copy_image(client: httpx.Client, url: str, key_stem: str) -> str | None:
    """Fetch one image under the URL rules and store it; its public URL, or None."""
    try:
        got = fetch_allowlisted(
            client,
            url,
            domains=MEDIA_DOMAINS,
            content_types=_IMAGE_EXTENSIONS.keys(),
            max_bytes=MAX_IMAGE_BYTES,
            headers=_auth_headers(url),
        )
    except FetchRefused as exc:
        logger.warning("reference media: %s", exc)
        return None
    key = f"{key_stem}.{_IMAGE_EXTENSIONS[got.content_type]}"
    try:
        return storage.put_image(key, got.data, got.content_type)
    except Exception:  # noqa: BLE001 — a storage outage costs this image, and the status records it
        logger.warning("reference media: storing %s failed", key, exc_info=True)
        return None


def capture_reference_media(
    asset_id: UUID,
    *,
    client: httpx.Client | None = None,
    open_db: OpenDb = _open_db,
) -> MediaStatus | None:
    """Copy a reference's cover and slides into project storage.

    Records ``{status, cover, slides, attempts, captured_at}`` under
    ``params["media"]`` whatever happened, so a failure is visible and
    retryable rather than a silent gap. Returns the status, or None when the
    row is gone. Never raises for a bad image; each one fails on its own.

    The row is read and written in two short sessions so no database
    connection is held while images download.
    """
    with open_db() as db:
        asset = db.get(ContentAsset, asset_id)
        if asset is None:
            return None
        project_id = asset.project_id
        params = asset.params or {}
        attempts = int((params.get("media") or {}).get("attempts") or 0)
        cover_src, slide_srcs = _media_sources(params.get("post") or {})

    stem = f"projects/{project_id}/{REFERENCE_ASSET_TYPE}/{asset_id}"
    own_client = client is None
    http = client or _new_media_client()
    try:
        cover = _copy_image(http, cover_src, f"{stem}/cover") if cover_src else None
        slides = [
            stored
            for i, src in enumerate(slide_srcs)
            if (stored := _copy_image(http, src, f"{stem}/slide-{i:02d}"))
        ]
    finally:
        if own_client:
            http.close()

    wanted = (1 if cover_src else 0) + len(slide_srcs)
    copied = (1 if cover else 0) + len(slides)
    if not wanted:
        status = MediaStatus.EMPTY
    elif copied == wanted:
        status = MediaStatus.OK
    else:
        status = MediaStatus.PARTIAL if copied else MediaStatus.FAILED
    media = {
        "status": status.value,
        # A slideshow's first slide is its cover when the post named none.
        "cover": cover or (slides[0] if slides else ""),
        "slides": slides,
        "attempts": attempts + 1,
        "captured_at": now_iso(),
    }

    with open_db() as db:
        asset = db.get(ContentAsset, asset_id)
        if asset is None:
            logger.info("reference media: asset %s was deleted during capture", asset_id)
            return None
        asset.params = {**(asset.params or {}), "media": media}
        db.add(asset)
        db.commit()
    logger.info(
        "reference media: %s for %s (%d of %d images)", status.value, asset_id, copied, wanted
    )
    return status


def capture_references_media(asset_ids: Iterable[UUID], *, open_db: OpenDb = _open_db) -> None:
    """Capture several references over one HTTP client. The background-task entry point."""
    with _new_media_client() as client:
        for asset_id in asset_ids:
            try:
                capture_reference_media(asset_id, client=client, open_db=open_db)
            except Exception:  # noqa: BLE001 — one reference's database error must not strand the rest of the batch
                logger.exception("reference media: capture failed for %s", asset_id)
