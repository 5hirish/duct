"""A crawl that runs while the user is still connecting a provider.

Onboarding's provider step takes the user 30–90 seconds; the crawl takes
about 30. Run serially, the one wait they will sit through is spent twice.
So the crawl detaches from the audit: ``start_prefetch`` fetches the root
page now — that is the "Found it — Acme?" confirmation, and it costs a second
— then crawls the rest in the background, and ``take_crawl`` hands the result
to ``run_pipeline`` when the session finally starts.

In-process, with a short TTL. A multi-replica deployment loses an entry on an
unlucky hop and the session simply crawls again: slower, never wrong. Move
this to the database only if the miss rate says so.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from agents.audit.draft import crawl_draft
from agents.audit.schema import CrawlPlan, CrawlResult, PageSignals
from service.crawl.extractor import extract_signals
from service.crawl.fetcher import SiteUnreachableError, assert_public_url, fetch, make_client

logger = logging.getLogger(__name__)

TTL_SECONDS = 15 * 60
# Bounded so an unauthenticated burst cannot grow the process; the limiter on
# the route is the first line, this is the second.
MAX_ENTRIES = 200

STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"

# A root that answers with one of these is a site telling the crawler to go
# away — a bot wall, a login, a rate limit — and the audit will be thin.
# Say so before the user waits for it.
_BLOCKED_STATUSES = frozenset({401, 403, 429, 503})


@dataclass
class Prefetch:
    crawl_id: str
    url: str
    owner_id: str
    root: PageSignals
    created_at: float = field(default_factory=time.monotonic)
    state: str = STATE_RUNNING
    result: CrawlResult | None = None
    error: str = ""
    task: asyncio.Task | None = None

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.created_at > TTL_SECONDS

    @property
    def blocked(self) -> bool:
        return self.root.http_status in _BLOCKED_STATUSES

    def site(self) -> dict[str, Any]:
        """The quick facts the URL screen shows back."""
        return {
            "url": self.root.url,
            "title": self.root.title,
            "description": self.root.meta_description or self.root.og_description,
            "favicon": self.root.favicon,
            "http_status": self.root.http_status,
            "is_spa_suspected": self.root.is_spa_suspected,
            "blocked": self.blocked,
        }

    def draft(self) -> dict[str, Any]:
        """Layer-1 draft from whatever has been read so far: the full crawl
        once it is in, the root page until then."""
        crawl = self.result or _single_page_result(self.url, self.root)
        return crawl_draft(crawl)

    def status(self) -> dict[str, Any]:
        return {
            "crawl_id": self.crawl_id,
            "state": self.state,
            "pages": len(self.result.pages) if self.result else 1,
            "error": self.error,
            "site": self.site(),
            "draft": self.draft(),
        }


_entries: dict[str, Prefetch] = {}


def _single_page_result(url: str, root: PageSignals) -> CrawlResult:
    return CrawlResult(plan=CrawlPlan(root_url=root.url or url, landing_pages=[root.url or url]), pages=[root])


def _prune() -> None:
    for key in [k for k, v in _entries.items() if v.expired]:
        entry = _entries.pop(key)
        if entry.task and not entry.task.done():
            entry.task.cancel()
    if len(_entries) > MAX_ENTRIES:
        oldest = sorted(_entries.values(), key=lambda e: e.created_at)[: len(_entries) - MAX_ENTRIES]
        for entry in oldest:
            _entries.pop(entry.crawl_id, None)


async def start_prefetch(url: str, *, owner_id: str, light: bool = False) -> Prefetch:
    """Validate, read the root page, and start the crawl in the background.

    Raises ``ValueError`` (from ``assert_public_url``) for an address the
    crawler must not touch and ``SiteUnreachableError`` when the root gives no
    HTTP response at all. Anything else — a 403, a bot wall — is a result, not
    an error: the entry reports it as ``blocked`` and the user decides.
    """
    _prune()
    await assert_public_url(url)
    async with make_client() as client:
        fetched = await fetch(client, url)
    if fetched.status == 0:
        raise SiteUnreachableError(url)
    # The address after redirects is the site's real one ("acme.com" →
    # "https://www.acme.com/"); it is what the project and the crawl use.
    final_url = fetched.redirect_chain[-1].get("url") if fetched.redirect_chain else url
    root = extract_signals(fetched.text, final_url or url, "landing_page", response_headers=fetched.headers)
    root.http_status = fetched.status

    entry = Prefetch(crawl_id=secrets.token_urlsafe(16), url=root.url or url, owner_id=owner_id, root=root)
    _entries[entry.crawl_id] = entry
    entry.task = asyncio.create_task(_crawl(entry, light))
    return entry


async def _crawl(entry: Prefetch, light: bool) -> None:
    from agents.audit.crawl import run_crawl

    try:
        entry.result = await run_crawl(entry.url, light=light)
        entry.state = STATE_DONE
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — recorded on the entry, never raised into the loop
        logger.warning("prefetch: crawl of %s failed: %s", entry.url, exc)
        entry.state = STATE_FAILED
        entry.error = str(exc)[:200]


def get_prefetch(crawl_id: str, *, owner_id: str | None = None) -> Prefetch | None:
    """The entry, if it is live and — when asked — belongs to ``owner_id``."""
    entry = _entries.get(crawl_id or "")
    if entry is None or entry.expired:
        return None
    if owner_id is not None and entry.owner_id != owner_id:
        return None
    return entry


async def take_crawl(crawl_id: str | None, *, owner_id: str | None = None, wait: float = 45.0) -> CrawlResult | None:
    """The finished crawl for ``crawl_id``, waiting briefly if it is still
    running. None when there is nothing to take — the caller crawls itself."""
    entry = get_prefetch(crawl_id or "", owner_id=owner_id)
    if entry is None:
        return None
    if entry.task is not None and not entry.task.done():
        try:
            await asyncio.wait_for(asyncio.shield(entry.task), timeout=wait)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001 — fall through to "not ready"
            pass
    return entry.result if entry.state == STATE_DONE else None
