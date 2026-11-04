"""The MCP Registry, searched by name from the Connections page (issue #496).

``presets.py`` kept the registry out because most of a search is noise: on
2026-11-03 "stripe" returned 17 servers and one was Stripe's, the rest
gateways that sit between a person and their account. What the registry does
prove is who owns each name. A reverse-DNS name (``com.notion``) means the
publisher proved notion.com; ``io.github.PostHog`` means they signed in to
GitHub as PostHog. That turns the question a person has, "is this the
vendor's own server?", into something checked rather than guessed:

* ``runs_host`` — the publisher owns the address the server runs at: the
  reverse-DNS domain is the host or a parent of it, or a GitHub login names
  the host's site (``getsentry`` for mcp.sentry.dev). A gateway that runs its
  own host passes; it is honest about being the gateway.
* ``official`` — that, and the host's site is the tool searched for:
  mcp.stripe.com for "stripe". Compared on the label before the TLD, so
  stripe.evil.com and stripecheckup.vercel.app are not Stripe's. Someone
  holding stripe.<another TLD> would pass; the card shows the host either way,
  and every call to a registry server asks first.

Kept: active, latest entries with a streamable-HTTP remote at a fixed public
https address. Dropped: local packages (npm, PyPI, Docker; the hosted agent
runs nothing), SSE-only remotes (the client speaks streamable HTTP), URL
templates (``{token}`` in an address is a credential in a URL), and a
required header other than ``Authorization`` (the key path sends a bearer
token and nothing else).

The registry's search is a substring match on the name, so the longest word
goes to it and every word must then appear in the name, title or
description. Each query is cached for ten minutes in process: the API runs
one worker, and the registry is a free public service worth not hammering.
What it returns is a third party's text, shown as text and never followed;
its addresses are canonicalised like a typed one.

The registry's address is the operator's (``MCP_REGISTRY_URL``), so this is
a plain client, not ``http.guarded_client``: a self-hosted registry on an
internal network is a legitimate choice the guard would refuse.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

import httpx

from config import get_configs
from service.mcp.http import UnsafeServerUrl, canonical_url
from service.mcp.oauth import AUTH_KEY

logger = logging.getLogger(__name__)

SEARCH_PATH = "/v0/servers"
PAGE_SIZE = 100  # the registry's maximum; one page is plenty for a name search
MAX_RESULTS = 30
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
CACHE_SECONDS = 600.0
CACHE_KEYS = 256
MAX_WORDS = 5
TITLE_CHARS = 80
DESCRIPTION_CHARS = 300
KEY_HINT_CHARS = 200

OFFICIAL_META = "io.modelcontextprotocol.registry/official"
STATUS_ACTIVE = "active"
TRANSPORT = "streamable-http"
AUTH_HEADER = "authorization"
GITHUB_NAMESPACE = "io.github."
# Name parts that say what every server is, so a title made from them says
# nothing: "com.stripe/mcp" is titled from its host instead.
GENERIC_WORDS = frozenset({"mcp", "server", "remote", "api"})
_TITLE_SUFFIX = re.compile(r"\s*\b(mcp\s+server|mcp|server)\s*$", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9][a-z0-9._-]*")

# A test swaps this for an ``httpx.MockTransport``; None is the real network.
_transport: httpx.AsyncBaseTransport | None = None
_cache: dict[str, tuple[float, list[Listing]]] = {}


class RegistryUnavailable(Exception):
    """The registry did not answer usably. The message is safe to show."""


@dataclass(frozen=True)
class Listing:
    """One registry server as the Connections page shows it."""

    name: str  # the registry's id, e.g. com.notion/mcp
    title: str
    description: str
    url: str  # canonical, what a connect sends
    host: str
    website: str
    auth: str  # AUTH_KEY when the registry says a key is required, else "" (discovery decides)
    key_hint: str  # the publisher's line about that key
    runs_host: bool
    official: bool

    def as_dict(self) -> dict:
        return asdict(self)


def enabled() -> bool:
    return bool(get_configs().mcp_registry_url.strip())


def words(query: str) -> list[str]:
    """The query's words, lowercased. One letter is not a search: "a" would
    match half the registry."""
    return [w for w in _WORD.findall((query or "").lower()) if len(w) >= 2][:MAX_WORDS]


def _site(host: str) -> str:
    """The label before the TLD: ``stripe`` for mcp.stripe.com. Wrong for a
    two-part suffix (co.uk), which only ever costs a server its Official tag."""
    labels = host.split(".")
    return labels[-2] if len(labels) >= 2 else labels[0]


def _namespace(name: str) -> str:
    return (name or "").split("/", 1)[0].strip()


def runs_host(name: str, host: str) -> bool:
    namespace = _namespace(name)
    if namespace.lower().startswith(GITHUB_NAMESPACE):
        login = re.sub(r"[^a-z0-9]", "", namespace[len(GITHUB_NAMESPACE):].lower())
        site = _site(host)
        return len(site) >= 3 and site in login
    domain = ".".join(reversed(namespace.lower().split(".")))
    return bool(domain) and (host == domain or host.endswith("." + domain))


def is_official(name: str, host: str, query_words: list[str]) -> bool:
    wanted = {*query_words, "".join(query_words), "-".join(query_words)}
    return runs_host(name, host) and _site(host) in wanted


def _clip(text: str, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _title(server: dict, host: str) -> str:
    given = _TITLE_SUFFIX.sub("", str(server.get("title") or "")).strip()
    if given:
        return _clip(given, TITLE_CHARS)
    part = str(server.get("name") or "").split("/", 1)[-1]
    kept = [w for w in re.split(r"[-_.\s]+", part) if w and w.lower() not in GENERIC_WORDS]
    if not kept:
        kept = [_site(host)]
    return _clip(" ".join(w[0].upper() + w[1:] for w in kept), TITLE_CHARS)


def _remote(server: dict) -> tuple[dict, dict | None] | None:
    """The first remote Duct can call, with its Authorization header if one is
    required, or None."""
    for remote in server.get("remotes") or []:
        url = str(remote.get("url") or "")
        if remote.get("type") != TRANSPORT or "{" in url or remote.get("variables"):
            continue
        required = [h for h in remote.get("headers") or [] if h.get("isRequired")]
        if any(str(h.get("name") or "").lower() != AUTH_HEADER for h in required):
            continue
        return remote, (required[0] if required else None)
    return None


def _website(server: dict) -> str:
    site = str(server.get("websiteUrl") or "")
    return site if site.startswith("https://") else ""


def parse(payload: dict, query_words: list[str]) -> list[Listing]:
    """The servers in one registry page a person can connect, best first."""
    found: list[tuple[tuple, Listing]] = []
    for index, item in enumerate(payload.get("servers") or []):
        server = item.get("server") or {}
        meta = (item.get("_meta") or {}).get(OFFICIAL_META) or {}
        if meta.get("status", STATUS_ACTIVE) != STATUS_ACTIVE or meta.get("isLatest") is False:
            continue
        picked = _remote(server)
        if picked is None:
            continue
        remote, key_header = picked
        try:
            url = canonical_url(str(remote.get("url") or ""))
        except UnsafeServerUrl:
            continue
        host = urlsplit(url).hostname or ""
        name = str(server.get("name") or "")
        text = " ".join([name, str(server.get("title") or ""), str(server.get("description") or "")]).lower()
        if not all(w in text for w in query_words):
            continue
        listing = Listing(
            name=name,
            title=_title(server, host),
            description=_clip(server.get("description"), DESCRIPTION_CHARS),
            url=url,
            host=host,
            website=_website(server),
            auth=AUTH_KEY if key_header else "",
            key_hint=_clip((key_header or {}).get("description"), KEY_HINT_CHARS),
            runs_host=runs_host(name, host),
            official=is_official(name, host, query_words),
        )
        first = query_words[0] if query_words else ""
        rank = (not listing.official, not listing.runs_host, not listing.title.lower().startswith(first), index)
        found.append((rank, listing))
    out: list[Listing] = []
    seen: set[str] = set()
    for _, listing in sorted(found, key=lambda pair: pair[0]):
        # Several entries can name one address (a vendor's and a copy of it);
        # the best-ranked one speaks for it.
        if listing.url not in seen:
            seen.add(listing.url)
            out.append(listing)
    return out[:MAX_RESULTS]


async def _fetch(term: str) -> dict:
    base = get_configs().mcp_registry_url.strip().rstrip("/")
    params = {"search": term, "limit": str(PAGE_SIZE), "version": "latest"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, transport=_transport) as http:
            response = await http.get(base + SEARCH_PATH, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:
        raise RegistryUnavailable("The MCP Registry didn't answer in time.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("mcp registry: search for %r failed: %s", term, exc)
        raise RegistryUnavailable("The MCP Registry couldn't be reached.") from exc


async def search(query: str) -> list[Listing]:
    query_words = words(query)
    if not enabled() or not query_words:
        return []
    key = " ".join(query_words)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    listings = parse(await _fetch(max(query_words, key=len)), query_words)
    if len(_cache) >= CACHE_KEYS:
        _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
    _cache[key] = (now, listings)
    return listings


def clear_cache() -> None:
    _cache.clear()
