"""RSS and Atom feeds as a connector (#564): a blog, a Substack, a changelog
page, a YouTube channel's uploads or a public repository's releases.atom.

One credential row holds every feed URL a project reads, one per line, and
one binding carries them all, which sidesteps the one-binding-per-type rule
on ``project_connectors``. The row is encrypted like any connector's, which
matters for a feed whose URL is the secret (a paid Substack, a private
podcast).

Every URL is user input aimed at the network, so three rules:

* **Public https only, pinned.** Each request, redirects included, goes
  through ``service.compatible._PinnedTransport``: the name is resolved once,
  every answer judged, and the connection made to the address that passed,
  so a rebinding has no second lookup to win.
* **Bounded.** ``MAX_FEEDS`` URLs, ``MAX_FEED_BYTES`` each, a short timeout,
  and a content type that says feed (or a body that plainly is one).
* **Parsed from bytes Duct fetched.** ``feedparser`` is never handed a URL,
  so it never makes a request of its own. Its XML parser is expat, whose
  entity-expansion limits stop the billion-laughs shape.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

from service.connectors import CAP_ACCOUNTS, ConnectorAuthContext, ConnectorMeta, register_connector

logger = logging.getLogger(__name__)

CONNECTOR_ID = "rss"
FEEDS_KEY = "feeds"
MAX_FEEDS = 10
MAX_FEED_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 15
MAX_ITEMS_PER_FEED = 50
MAX_SUMMARY_CHARS = 280
USER_AGENT = "Duct feed reader (+https://getduct.ai)"

FEED_TYPES = frozenset({
    "application/rss+xml", "application/atom+xml", "application/rdf+xml",
    "application/xml", "text/xml", "application/x-rss+xml",
})
_FEED_ROOTS = (b"<rss", b"<feed", b"<rdf:RDF")
SNIFF_BYTES = 2048
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def parse_urls(text: str) -> list[str]:
    """The feed URLs typed into the card: one per line (commas and spaces
    also split), https only, duplicates dropped, at most ``MAX_FEEDS``.
    ValueError, worded for the card, on anything else."""
    from service.crawl.fetcher import SSRFError, validate_public_url

    urls: list[str] = []
    for raw in re.split(r"[\s,]+", text or ""):
        url = raw.strip()
        if not url:
            continue
        if urlparse(url).scheme.lower() != "https":
            raise ValueError(f"Feed addresses must start with https:// ({url}).")
        try:
            validate_public_url(url)
        except SSRFError as exc:
            raise ValueError(f"{url} is not a public address Duct can read.") from exc
        if url not in urls:
            urls.append(url)
    if not urls:
        raise ValueError("Add at least one feed address, one per line.")
    if len(urls) > MAX_FEEDS:
        raise ValueError(f"Up to {MAX_FEEDS} feeds per project; this list has {len(urls)}.")
    return urls


def feeds_id(urls: list[str]) -> str:
    """One stable account id for the whole list, so the binding is one row."""
    return "feeds:" + hashlib.sha256("\n".join(sorted(urls)).encode()).hexdigest()[:16]


def fetch_bytes(url: str) -> bytes:
    """One feed's body, through the pinned public transport. RuntimeError,
    worded for the card, when it cannot be read or is not a feed."""
    import httpx2

    from service.compatible import _PinnedTransport

    try:
        with httpx2.Client(transport=_PinnedTransport(), timeout=TIMEOUT_SECONDS, follow_redirects=True,
                           max_redirects=3, trust_env=False, headers={"User-Agent": USER_AGENT}) as client:
            with client.stream("GET", url) as res:
                if res.status_code != 200:
                    raise RuntimeError(f"{url} answered {res.status_code}.")
                kind = (res.headers.get("content-type") or "").split(";")[0].strip().lower()
                body = bytearray()
                for chunk in res.iter_bytes():
                    body += chunk
                    if len(body) > MAX_FEED_BYTES:
                        raise RuntimeError(f"{url} is larger than {MAX_FEED_BYTES // (1024 * 1024)} MB.")
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001 — a refused address, a timeout, TLS: the card says which feed
        raise RuntimeError(f"{url} could not be read ({type(exc).__name__}).") from exc
    data = bytes(body)
    if kind not in FEED_TYPES and not looks_like_feed(data):
        raise RuntimeError(f"{url} is a web page, not a feed. Use the page's RSS or Atom link.")
    return data


def looks_like_feed(head: bytes) -> bool:
    """Whether a body opens on a feed's root element, past an XML declaration,
    a doctype or comments. A scan, not a regex: a pattern over repeated
    comments backtracks exponentially on a crafted body (CodeQL, #566)."""
    rest = head[:SNIFF_BYTES].lstrip()
    while rest.startswith((b"<?", b"<!--", b"<!")):
        closer = b"?>" if rest.startswith(b"<?") else b"-->" if rest.startswith(b"<!--") else b">"
        end = rest.find(closer)
        if end < 0:
            return False
        rest = rest[end + len(closer):].lstrip()
    return rest.startswith(_FEED_ROOTS)


def _clip(text: Any, limit: int = MAX_SUMMARY_CHARS) -> str:
    plain = _SPACE.sub(" ", _TAGS.sub(" ", str(text or ""))).strip()
    return plain if len(plain) <= limit else plain[: limit - 1].rstrip() + "…"


def _when(entry: Any) -> date | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        stamp = entry.get(key)
        if stamp:
            return datetime(*stamp[:6], tzinfo=timezone.utc).date()
    return None


def parse_feed(data: bytes, url: str) -> dict[str, Any]:
    """A feed's title and its entries as rows: title, link, published, summary."""
    import feedparser

    parsed = feedparser.parse(data)
    if parsed.get("bozo") and not parsed.get("entries"):
        raise RuntimeError(f"{url} is not a feed Duct can read.")
    title = _clip((parsed.get("feed") or {}).get("title") or urlparse(url).hostname or url, 120)
    rows = []
    for entry in (parsed.get("entries") or [])[:MAX_ITEMS_PER_FEED]:
        when = _when(entry)
        rows.append({
            "feed": title,
            "feed_url": url,
            "title": _clip(entry.get("title"), 200),
            "link": str(entry.get("link") or ""),
            "published": when.isoformat() if when else "",
            "summary": _clip(entry.get("summary")),
        })
    return {"title": title, "rows": rows}


def fetch_rss(creds: dict[str, str], date_from: str, date_to: str) -> dict[str, Any]:
    """Every feed's entries published inside ``[date_from, date_to]``. A feed
    that fails is named in ``errors``; the others still come back."""
    urls = parse_urls(creds.get(FEEDS_KEY) or "")
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    data: list[dict[str, Any]] = []
    errors: list[str] = []
    for url in urls:
        try:
            feed = parse_feed(fetch_bytes(url), url)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        data += [r for r in feed["rows"] if r["published"] and start <= date.fromisoformat(r["published"]) <= end]
    data.sort(key=lambda r: r["published"], reverse=True)
    return {
        "summary": {"feeds": len(urls), "items": len(data), "window": {"from": date_from, "to": date_to}},
        "data": data,
        "errors": errors,
    }


class RssConnector:
    """Feed URLs typed into the card; checked by reading each once on save."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        urls = parse_urls(str(dict(auth.extras).get(FEEDS_KEY) or ""))  # ValueError → 422
        titles: list[str] = []
        for url in urls:
            try:
                titles.append(parse_feed(fetch_bytes(url), url)["title"])
            except RuntimeError as exc:
                raise ValueError(str(exc)) from exc
        name = titles[0] if len(titles) == 1 else f"{titles[0]} and {len(titles) - 1} more"
        return [{"account_id": feeds_id(urls), "account_name": name}]


RSS_META = ConnectorMeta(
    id=CONNECTOR_ID,
    label="RSS and Atom feeds",
    oauth_scope=None,  # public feeds; a private one carries its secret in the URL
    capabilities=frozenset({CAP_ACCOUNTS}),
    entity_noun="feed list",
    entity_noun_plural="feed lists",
)

register_connector(RSS_META, RssConnector())
