"""Sitemap discovery, parsing, and page classification for the SEO audit crawler."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import httpx

from agents.audit.schema import CrawlPlan
from service.crawl.fetcher import SSRFError, fetch_text, validate_public_url

logger = logging.getLogger(__name__)

_BLOG_PATH_PATTERNS = re.compile(
    r"/(blog|posts?|articles?|news|insights?|resources?)/",
    re.IGNORECASE,
)

_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}

MAX_LANDING_PAGES = 30
MAX_BLOG_POSTS = 5
MAX_CHILD_SITEMAPS = 5


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/") or url


def _is_blog(url: str) -> bool:
    return bool(_BLOG_PATH_PATTERNS.search(url))


def _parse_urlset(xml_text: str) -> list[dict]:
    """Parse a <urlset> sitemap. Returns list of {loc, lastmod}."""
    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.debug("sitemap parse error: %s", exc)
        return entries

    tag_loc = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
    tag_lastmod = "{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod"

    for url_el in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
        loc_el = url_el.find(tag_loc)
        lastmod_el = url_el.find(tag_lastmod)
        if loc_el is not None and loc_el.text:
            entries.append({
                "loc": loc_el.text.strip(),
                "lastmod": (lastmod_el.text or "").strip() if lastmod_el is not None else "",
            })
    return entries


def _parse_sitemapindex(xml_text: str) -> list[str]:
    """Parse a <sitemapindex>. Returns list of child sitemap URLs."""
    child_urls = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return child_urls
    tag_loc = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
    for sm_el in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap"):
        loc_el = sm_el.find(tag_loc)
        if loc_el is not None and loc_el.text:
            child_urls.append(loc_el.text.strip())
    return child_urls


def _is_sitemapindex(xml_text: str) -> bool:
    return "<sitemapindex" in xml_text


def _extract_sitemap_from_robots(robots_txt: str, base_url: str) -> str:
    """Extract the first Sitemap: directive from robots.txt content.

    Uses urllib.robotparser for RFC-compliant parsing (handles Allow/Disallow,
    wildcards, comments) rather than brittle line-by-line string matching.
    Falls back to manual scan if the parser returns nothing.
    """
    import urllib.robotparser
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    # RobotFileParser.site_maps() returns the Sitemap: directives (Python 3.8+)
    maps = rp.site_maps()
    if maps:
        return maps[0]
    # Manual fallback for edge cases where the parser finds nothing
    for line in robots_txt.splitlines():
        if line.lower().startswith("sitemap:"):
            return line.split(":", 1)[1].strip()
    return ""


async def _fetch_all_entries(
    client: httpx.AsyncClient,
    sitemap_url: str,
    depth: int = 0,
) -> list[dict]:
    """Recursively fetch sitemap entries. Max depth 1 (index → children)."""
    if depth > 1:
        return []
    text, status = await fetch_text(client, sitemap_url)
    if not text or status not in range(200, 300):
        return []
    if _is_sitemapindex(text):
        child_urls = _parse_sitemapindex(text)[:MAX_CHILD_SITEMAPS]
        all_entries: list[dict] = []
        for child_url in child_urls:
            entries = await _fetch_all_entries(client, child_url, depth=depth + 1)
            all_entries.extend(entries)
        return all_entries
    return _parse_urlset(text)


def _bare_host(netloc: str) -> str:
    """Strip www. prefix and port for same-origin comparison.

    Allows matching when the root URL uses the apex domain but the sitemap
    uses the www subdomain (or vice-versa), which is common on SPAs/CDNs.
    """
    return netloc.lower().removeprefix("www.").split(":")[0]


def _is_html_body(text: str) -> bool:
    """Return True if text looks like an HTML document rather than plain text."""
    snippet = text.lstrip()[:100].lower()
    return snippet.startswith("<!doctype html") or snippet.startswith("<html")


async def fetch_crawl_plan(
    client: httpx.AsyncClient,
    root_url: str,
    max_blog_posts: int = MAX_BLOG_POSTS,
    light: bool = False,
) -> CrawlPlan:
    """Discover and classify pages from the site's sitemap.

    light=True  → top 5 pages or 20% of sitemap entries, max 15 (for quick checks/tests).
    light=False → full crawl up to MAX_LANDING_PAGES + max_blog_posts (default).
    """
    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    root_bare = _bare_host(parsed.netloc)

    robots_url = urljoin(base, "/robots.txt")
    llms_txt_url = urljoin(base, "/llms.txt")

    # Discover sitemap URL — must be on the same domain as the input.
    # Cross-domain sitemap references in robots.txt are ignored: the site may
    # point to a sitemap they don't own (misconfiguration) and we must not
    # crawl pages on a domain the user didn't ask to audit.
    robots_text, _ = await fetch_text(client, robots_url)
    robots_sitemap = _extract_sitemap_from_robots(robots_text, base)
    if robots_sitemap and _bare_host(urlparse(robots_sitemap).netloc) == root_bare:
        sitemap_url = robots_sitemap
    else:
        if robots_sitemap:
            logger.info(
                "sitemap in robots.txt (%s) is on a different domain than %s — ignoring",
                robots_sitemap, root_bare,
            )
        sitemap_url = ""

    if not sitemap_url:
        # Try common locations on the input domain
        for candidate in ["/sitemap.xml", "/sitemap-index.xml", "/sitemap_index.xml"]:
            candidate_url = urljoin(base, candidate)
            _, status = await fetch_text(client, candidate_url)
            if status in range(200, 300):
                sitemap_url = candidate_url
                break

    all_entries: list[dict] = []
    if sitemap_url:
        all_entries = await _fetch_all_entries(client, sitemap_url)

    total = len(all_entries)

    # Filter: same domain as input (www variants allowed), publicly routable only.
    def _is_safe_entry(e: dict) -> bool:
        loc_netloc = urlparse(e["loc"]).netloc
        if _bare_host(loc_netloc) != root_bare:
            return False
        try:
            validate_public_url(e["loc"])
            return True
        except SSRFError:
            return False

    all_entries = [
        e for e in all_entries
        if _is_safe_entry(e)
    ]

    # Classify
    blog_entries = [e for e in all_entries if _is_blog(e["loc"])]
    landing_entries = [e for e in all_entries if not _is_blog(e["loc"])]

    # Sort blog posts by lastmod desc, take top N
    blog_entries.sort(key=lambda e: e.get("lastmod", ""), reverse=True)

    if light:
        # Light pass: top 5 pages or 20% of total entries, whichever is smaller, max 15.
        light_cap = min(5, max(1, int(total * 0.20)), 15)
        selected_landings = [_normalize_url(e["loc"]) for e in landing_entries[:light_cap]]
        selected_blogs = [_normalize_url(e["loc"]) for e in blog_entries[:1]]
    else:
        selected_landings = [_normalize_url(e["loc"]) for e in landing_entries[:MAX_LANDING_PAGES]]
        selected_blogs = [_normalize_url(e["loc"]) for e in blog_entries[:max_blog_posts]]

    # Ensure root URL is included even if not in sitemap
    norm_root = _normalize_url(root_url)
    if norm_root not in selected_landings:
        selected_landings.insert(0, norm_root)

    return CrawlPlan(
        root_url=norm_root,
        sitemap_url=sitemap_url,
        robots_txt_url=robots_url,
        llms_txt_url=llms_txt_url,
        landing_pages=selected_landings,
        blog_posts=selected_blogs,
        total_sitemap_urls=total,
    )
