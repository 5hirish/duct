"""Turn a pasted TikTok link into a saved reference a clone can be built on.

The clone flow (issue #222) starts from text somebody pasted, and that text
decides two things we pay for: an Apify actor run, and the reference whose
pictures get copied into project storage. So it is never passed on as typed.
``parse_tiktok_post_url`` reduces it to a handle and a numeric post id, and
everything downstream uses the URL rebuilt from those two parts. A query
string, a fragment, userinfo, a port, a lookalike host: none of it survives,
because none of it is read. Nothing here fetches the pasted URL itself; the
only fetches are Apify's API and, through ``service/discovery``, the image CDN
behind its allowlist.

The actor input is bounded here too (``single_post_run_input``): one post,
every download off. It takes a parsed ``TikTokPost`` rather than a string, so
an unvalidated URL cannot reach it, and it is a function rather than a dict at
the call site so it can move next to the Discover inputs in
``service/apify/policy.py``.

A post the project already saved (Discover's save, or an earlier clone) is
reused: no second run, no second copy of its pictures. Otherwise the scraped
post goes through ``ingest_reference`` and ``capture_reference_media``, the
same two steps a Discover save runs.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlmodel import select

from config import get_configs
from models.content import ContentAsset
from service import storage
from service.apify import ApifyAPIError, ApifyClient, ApifyRunStatus, ScrapedPost, run_cache
from service.discovery import (
    REFERENCE_ASSET_TYPE,
    OpenDb,
    _open_db,
    capture_reference_media,
    ingest_reference,
    needs_media,
)

logger = logging.getLogger(__name__)

# The single-post scraper. The API spelling (``user~actor``), because that is
# the one ``/v2/acts/{id}/runs`` resolves.
SINGLE_POST_ACTOR = "clockworks~tiktok-scraper"

# Exact hosts, never a suffix match: a clone reads one post on TikTok's own
# site, and nothing about that needs a subdomain we have not named.
TIKTOK_HOSTS = frozenset({"tiktok.com", "www.tiktok.com", "m.tiktok.com"})

# Share links carry no post id; resolving one means following a redirect we
# would have to make ourselves. Named so the refusal can say what to do.
SHORT_LINK_HOSTS = frozenset({"vm.tiktok.com", "vt.tiktok.com"})

# TikTok usernames are letters, digits, underscores and full stops (24 today;
# the slack is for the day that changes). Post ids are snowflakes, all digits.
_HANDLE_RE = re.compile(r"[A-Za-z0-9._]{1,64}")
_POST_ID_RE = re.compile(r"\d{8,25}")
_POST_KINDS = frozenset({"video", "photo"})

# Nobody pastes a post link this long; a paste that is has something else in it.
MAX_URL_CHARS = 2048

# One post takes the actor 15-40 s. The ceiling is for a slow Apify queue, and
# the run is left to finish on its own: it is one post, and a retry inside the
# reuse window joins it instead of paying again (service/apify/run_cache.py).
SCRAPE_TIMEOUT_SECONDS = 150.0
SCRAPE_POLL_SECONDS = 3.0

_DEAD_RUN = frozenset({
    ApifyRunStatus.FAILED,
    ApifyRunStatus.ABORTING,
    ApifyRunStatus.ABORTED,
    ApifyRunStatus.TIMING_OUT,
    ApifyRunStatus.TIMED_OUT,
})

# The diagnosis looks at the carousel, not a sample of it: TikTok caps photo
# mode at 35 images and a performing carousel sits at 6-13, so eight covers the
# hook, the arc and the payoff without paying for the long tail.
MAX_DIAGNOSIS_IMAGES = 8
# Anthropic rejects an image over 5 MB; a TikTok slide is a few hundred KB.
MAX_DIAGNOSIS_IMAGE_BYTES = 4 * 1024 * 1024
# What a vision model accepts. AVIF is stored (service/discovery.py) but no
# chat API reads it, so it is skipped rather than sent to be refused.
_VISION_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

# Which public count a post won on, from the counts alone. Watch time and
# completion are the strongest signals and are invisible in public data, so
# this is a prior the model is told to overrule: shares and saves outweigh
# comments and likes per view, likes least of all.
_LEVER_WEIGHTS = {"shares": 3.0, "saves": 2.5, "comments": 2.5, "likes": 1.0}


class InvalidTikTokUrl(ValueError):
    """The pasted text is not a link to one TikTok post.

    A ``ValueError`` so a Pydantic validator turns it into a 422, and the
    message is written for the person who pasted the link.
    """


class ReferenceUnavailable(RuntimeError):
    """The post could not be read: private, deleted, or the scrape failed.

    Classified by name in ``agents/core/errors.py`` (``reference_unavailable``),
    so the message here is for the log and never reaches the browser.
    """


@dataclass(frozen=True)
class TikTokPost:
    """A validated pointer to one public TikTok post."""

    handle: str
    post_id: str

    @property
    def url(self) -> str:
        # ``/video/`` for photo posts too: it is the form the actor itself
        # returns as ``webVideoUrl``, so a pasted link and a saved reference
        # name a post the same way, and TikTok serves a photo post at it.
        return f"https://www.tiktok.com/@{self.handle}/video/{self.post_id}"


def parse_tiktok_post_url(raw: str) -> TikTokPost:
    """The post a pasted link names, or ``InvalidTikTokUrl`` saying why not.

    Accepts what a browser's address bar or TikTok's "copy link" gives on the
    web: ``https://www.tiktok.com/@creator/video/<id>`` (or ``/photo/``), with
    or without the scheme, with whatever tracking query TikTok appended.
    """
    text = (raw or "").strip()
    if not text or len(text) > MAX_URL_CHARS:
        raise InvalidTikTokUrl("Paste the link to one TikTok post.")
    if "://" not in text:
        text = f"https://{text}"
    try:
        parts = urlsplit(text)
        port = parts.port  # raises on a malformed port
    except ValueError as exc:
        raise InvalidTikTokUrl("That doesn't look like a link.") from exc
    host = (parts.hostname or "").rstrip(".").lower()
    if (
        parts.scheme not in ("https", "http")
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 80, 443)
    ):
        raise InvalidTikTokUrl("That link is not a TikTok post.")
    segments = [s for s in parts.path.split("/") if s]
    if host in SHORT_LINK_HOSTS or (host in TIKTOK_HOSTS and segments[:1] == ["t"]):
        raise InvalidTikTokUrl(
            "That is a TikTok share link. Open it, then copy the full address "
            "(tiktok.com/@creator/video/…)."
        )
    if host not in TIKTOK_HOSTS:
        raise InvalidTikTokUrl("That link is not on tiktok.com.")
    if (
        len(segments) != 3
        or not segments[0].startswith("@")
        or not _HANDLE_RE.fullmatch(segments[0][1:])
        or segments[1] not in _POST_KINDS
        or not _POST_ID_RE.fullmatch(segments[2])
    ):
        raise InvalidTikTokUrl(
            "That link is not a single TikTok post. It should look like "
            "tiktok.com/@creator/video/1234567890."
        )
    return TikTokPost(handle=segments[0][1:], post_id=segments[2])


def single_post_run_input(post: TikTokPost) -> dict[str, Any]:
    """The whole actor input for reading one post. Nothing else is ever sent."""
    return {
        "postURLs": [post.url],
        "resultsPerPage": 1,
        # Off, and said so rather than left to the actor's defaults: the cover
        # and slides are copied from TikTok's CDN by capture_reference_media,
        # which costs nothing, while the actor's own downloads are billed per
        # file and land in a token-gated key-value store.
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadSubtitles": False,
    }


async def scrape_post(
    client: ApifyClient,
    post: TikTokPost,
    *,
    timeout: float = SCRAPE_TIMEOUT_SECONDS,
    poll: float = SCRAPE_POLL_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[ScrapedPost, dict[str, Any]]:
    """Run the actor on one post and return it with its provenance.

    Starts through the run cache, so the same link inside its window joins the
    earlier run. Raises ``ReferenceUnavailable`` for every way it can fail,
    including a run that answers with some other post than the one asked for.
    """
    payload = single_post_run_input(post)
    try:
        run, reused = await run_cache.apify_runs.start(client, SINGLE_POST_ACTOR, payload)
        waited = 0.0
        while run.status is not ApifyRunStatus.SUCCEEDED and run.status not in _DEAD_RUN:
            if waited >= timeout:
                raise ReferenceUnavailable(f"run {run.id} still {run.status.value} after {timeout:.0f}s")
            await sleep(poll)
            waited += poll
            run = await client.get_run(run.id)
        if run.status is not ApifyRunStatus.SUCCEEDED:
            raise ReferenceUnavailable(f"run {run.id} ended {run.status.value}")
        items = await client.get_dataset_posts(run.default_dataset_id, limit=1)
    except ApifyAPIError as exc:
        raise ReferenceUnavailable(f"Apify {exc.status_code}: {exc.message}") from exc
    except ValueError as exc:  # an id Apify returned that its own client refuses
        raise ReferenceUnavailable(str(exc)) from exc
    scraped = next((item for item in items if item.id == post.post_id), None)
    if scraped is None:
        raise ReferenceUnavailable(f"run {run.id} returned no post {post.post_id}")
    logger.info("clone: %s run %s for post %s", "reused" if reused else "started", run.id, post.post_id)
    provenance = {
        "actor_id": SINGLE_POST_ACTOR,
        "run_id": run.id,
        "dataset_id": run.default_dataset_id,
        "request": payload,
    }
    return scraped, provenance


@dataclass(frozen=True)
class CloneReference:
    """A saved reference, read once, for the clone run to work from."""

    asset_id: UUID
    url: str
    post: dict[str, Any]   # the saved ScrapedPost, snake_case
    media: dict[str, Any]  # params["media"]: what capture copied, if anything
    reused: bool           # already saved in this project; nothing was scraped

    @property
    def author(self) -> str:
        return str((self.post.get("author_meta") or {}).get("name") or "")

    @property
    def slide_urls(self) -> list[str]:
        return [u for u in (self.media.get("slides") or []) if isinstance(u, str) and u]


def _snapshot(asset: ContentAsset, *, reused: bool) -> CloneReference:
    params = asset.params or {}
    return CloneReference(
        asset_id=asset.id,
        url=asset.url,
        post=dict(params.get("post") or {}),
        media=dict(params.get("media") or {}),
        reused=reused,
    )


def _saved(open_db: OpenDb, project_id: UUID, post_id: str) -> CloneReference | None:
    # Keyed the way ingest_reference keys a post, so Discover's saves count.
    with open_db() as db:
        asset = db.exec(
            select(ContentAsset).where(
                ContentAsset.project_id == project_id,
                ContentAsset.asset_type == REFERENCE_ASSET_TYPE,
                ContentAsset.filename == f"tiktok-{post_id}",
            )
        ).first()
        return _snapshot(asset, reused=True) if asset is not None else None


def _ingest(
    open_db: OpenDb, project_id: UUID, scraped: ScrapedPost, provenance: Mapping[str, Any]
) -> CloneReference:
    with open_db() as db:
        return _snapshot(ingest_reference(db, project_id, scraped, provenance=provenance), reused=False)


def _reload(open_db: OpenDb, asset_id: UUID, *, reused: bool) -> CloneReference | None:
    with open_db() as db:
        asset = db.get(ContentAsset, asset_id)
        return _snapshot(asset, reused=reused) if asset is not None else None


def _apify_client() -> ApifyClient | None:
    key = (get_configs().apify_api_key or "").strip()
    return ApifyClient(key) if key else None


async def resolve_clone_reference(
    project_id: UUID,
    post: TikTokPost,
    *,
    apify: Callable[[], ApifyClient | None] = _apify_client,
    open_db: OpenDb = _open_db,
) -> CloneReference:
    """The project's reference for *post*: reused if saved, else scraped and saved.

    Its pictures are copied before this returns when they have not been yet,
    because the clone's diagnosis looks at them and the reference exists to be
    looked at later. A capture that fails leaves a reference without pictures,
    which is still a reference: the diagnosis works from the caption and counts.
    """
    reference = await asyncio.to_thread(_saved, open_db, project_id, post.post_id)
    if reference is None:
        client = apify()
        if client is None:
            raise ReferenceUnavailable("APIFY_API_KEY is not set on this instance")
        async with client as c:
            scraped, provenance = await scrape_post(c, post)
        reference = await asyncio.to_thread(_ingest, open_db, project_id, scraped, provenance)
    if needs_media({"media": reference.media}):
        await asyncio.to_thread(capture_reference_media, reference.asset_id, open_db=open_db)
        reference = await asyncio.to_thread(
            _reload, open_db, reference.asset_id, reused=reference.reused
        ) or reference
    return reference


def reference_images(
    reference: CloneReference, *, limit: int = MAX_DIAGNOSIS_IMAGES
) -> list[tuple[bytes, str]]:
    """The reference's copied pictures as ``(bytes, mime)``, slides first.

    Read back from project storage, never from TikTok: these are URLs capture
    wrote. A carousel's cover is its first slide, so the cover is used only
    when there are no slides (a video).
    """
    urls = reference.slide_urls or ([reference.media["cover"]] if reference.media.get("cover") else [])
    images: list[tuple[bytes, str]] = []
    for url in urls[:limit]:
        mime = _VISION_TYPES.get(PurePosixPath(urlsplit(url).path).suffix.lower())
        if mime is None:
            continue
        try:
            data = storage.get_bytes(url)
        except Exception:  # noqa: BLE001 — an unreadable picture costs the diagnosis that picture
            logger.warning("clone: could not read %s back from storage", url, exc_info=True)
            continue
        if data and len(data) <= MAX_DIAGNOSIS_IMAGE_BYTES:
            images.append((data, mime))
    return images


def engagement_prior(post: Mapping[str, Any]) -> dict[str, Any]:
    """Rates per view, reach against the creator's following, and a crude lever.

    Plain arithmetic over public counts, so the diagnosis starts from numbers
    rather than adjectives. ``lever`` is None when there are no views to divide
    by; every rate is None in that case too.
    """
    views = int(post.get("play_count") or 0)
    counts = {
        "likes": int(post.get("digg_count") or 0),
        "comments": int(post.get("comment_count") or 0),
        "shares": int(post.get("share_count") or 0),
        "saves": int(post.get("collect_count") or 0),
    }
    followers = int((post.get("author_meta") or {}).get("fans") or 0)
    rates = {name: (round(n / views, 4) if views else None) for name, n in counts.items()}
    scored = {name: rate * _LEVER_WEIGHTS[name] for name, rate in rates.items() if rate is not None}
    return {
        "views": views,
        **counts,
        "followers": followers,
        "rates": rates,
        "reach_multiple": round(views / followers, 1) if views and followers else None,
        "lever": max(scored, key=scored.__getitem__) if scored else None,
    }


__all__ = [
    "CloneReference",
    "InvalidTikTokUrl",
    "MAX_DIAGNOSIS_IMAGES",
    "ReferenceUnavailable",
    "SINGLE_POST_ACTOR",
    "TikTokPost",
    "engagement_prior",
    "parse_tiktok_post_url",
    "reference_images",
    "resolve_clone_reference",
    "scrape_post",
    "single_post_run_input",
]
