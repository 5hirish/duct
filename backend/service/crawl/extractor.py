"""HTML signal extractor for the SEO audit crawler.

Uses selectolax (Lexbor HTML5 engine — same parser Chrome uses) for fast,
browser-accurate parsing of real-world HTML. Replaces the stdlib html.parser
state machine which was fragile against malformed markup.

Extracts per-page SEO signals:
  - Head: title, meta description, canonical, noindex, hreflang
  - OG/social: og:title/description/image/type, twitter:card/image
  - Structure: h1/h2 text, JSON-LD @types, structured data presence
  - Images: count + images missing alt
  - Links: internal + external URLs with anchor text (parallel arrays)
  - Content: approximate word count, body text snippet (first 500 chars)
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin, urlparse

from agents.audit.schema import PageSignals

logger = logging.getLogger(__name__)

# Noise elements whose text we exclude from word count / body snippet.
# selectolax lets us remove these before extracting body text.
_NOISE_SELECTORS = [
    "script", "style", "noscript", "nav", "footer", "header",
    "[role='navigation']", "[role='banner']", "[role='contentinfo']",
    ".nav", ".navigation", ".menu", ".footer", ".header", ".sidebar",
    "#nav", "#navigation", "#menu", "#footer", "#header", "#sidebar",
]

_BODY_SNIPPET_LEN = 500
_MAX_INTERNAL_LINKS = 50
_MAX_EXTERNAL_LINKS = 20


def _get_text(node) -> str:
    """Get cleaned visible text from a node, stripping child tags."""
    if node is None:
        return ""
    return (node.text(deep=True, strip=True) or "").strip()


def _attr(node, name: str, default: str = "") -> str:
    if node is None:
        return default
    return (node.attributes.get(name) or default).strip()


def extract_signals(html: str, url: str, page_type: str = "other") -> PageSignals:
    """Parse *html* and return a PageSignals instance for *url*."""
    try:
        from selectolax.parser import HTMLParser as SParser
    except ImportError:
        logger.warning("selectolax not installed, falling back to stdlib html.parser")
        return _extract_signals_stdlib(html, url, page_type)

    try:
        tree = SParser(html)
    except Exception as exc:
        logger.debug("selectolax parse error for %s: %s", url, exc)
        return PageSignals(url=url, page_type=page_type)  # type: ignore[arg-type]

    base_netloc = urlparse(url).netloc

    # ------------------------------------------------------------------
    # <head> signals
    # ------------------------------------------------------------------

    title = _get_text(tree.css_first("title"))

    meta_desc_node = tree.css_first('meta[name="description"]')
    meta_description = _attr(meta_desc_node, "content")

    canonical_node = tree.css_first('link[rel="canonical"]')
    canonical = _attr(canonical_node, "href")

    # noindex: <meta name="robots" content="noindex,...">
    robots_node = tree.css_first('meta[name="robots"]')
    robots_content = _attr(robots_node, "content").lower()
    is_noindex = "noindex" in robots_content

    # hreflang: collect all lang values
    hreflang_langs = [
        _attr(node, "hreflang")
        for node in tree.css('link[rel="alternate"][hreflang]')
        if _attr(node, "hreflang")
    ]

    # ------------------------------------------------------------------
    # Open Graph + social
    # ------------------------------------------------------------------

    def _og(prop: str) -> str:
        node = tree.css_first(f'meta[property="og:{prop}"]')
        return _attr(node, "content")

    def _twitter(name: str) -> str:
        node = tree.css_first(f'meta[name="twitter:{name}"]')
        return _attr(node, "content")

    og_title = _og("title")
    og_description = _og("description")
    og_image = _og("image")
    og_type = _og("type")
    twitter_card = _twitter("card")
    twitter_image = _twitter("image")

    # ------------------------------------------------------------------
    # Headings
    # ------------------------------------------------------------------

    h1s = [_get_text(n) for n in tree.css("h1") if _get_text(n)][:5]
    h2s = [_get_text(n) for n in tree.css("h2") if _get_text(n)][:8]

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------

    images = tree.css("img")
    image_count = len(images)
    images_missing_alt = sum(
        1 for img in images
        if not (img.attributes.get("alt") or "").strip()
    )

    # ------------------------------------------------------------------
    # JSON-LD structured data
    # ------------------------------------------------------------------

    schema_types: list[str] = []
    for script in tree.css('script[type="application/ld+json"]'):
        raw = script.text(strip=True)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            _collect_schema_types(obj, schema_types)
        except (json.JSONDecodeError, ValueError):
            pass

    # ------------------------------------------------------------------
    # Links (with anchor text)
    # ------------------------------------------------------------------

    internal_links: list[str] = []
    internal_link_anchors: list[str] = []
    external_links: list[str] = []
    external_link_anchors: list[str] = []

    seen_internal: set[str] = set()
    seen_external: set[str] = set()

    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(url, href)
        parsed = urlparse(full)
        if not parsed.scheme.startswith("http"):
            continue
        anchor = _get_text(a) or ""
        netloc = parsed.netloc

        if netloc == base_netloc:
            if full not in seen_internal and len(internal_links) < _MAX_INTERNAL_LINKS:
                seen_internal.add(full)
                internal_links.append(full)
                internal_link_anchors.append(anchor)
        elif netloc and full not in seen_external and len(external_links) < _MAX_EXTERNAL_LINKS:
            seen_external.add(full)
            external_links.append(full)
            external_link_anchors.append(anchor)

    # ------------------------------------------------------------------
    # Body text: word count + snippet
    # Remove noise nodes in-place, then extract text from remaining body.
    # ------------------------------------------------------------------

    word_count_approx = 0
    body_text_snippet = ""

    body = tree.css_first("body")
    if body:
        # Strip nav/header/footer/script/style noise before text extraction
        for noise_sel in ("nav", "header", "footer", "script", "style", "noscript",
                          "[role='navigation']", "[role='banner']", "[role='contentinfo']"):
            for node in tree.css(noise_sel):
                node.decompose()

        full_text = re.sub(r"\s+", " ", body.text(deep=True, separator=" ", strip=True)).strip()
        word_count_approx = len(full_text.split())
        body_text_snippet = full_text[:_BODY_SNIPPET_LEN]

    return PageSignals(
        url=url,
        page_type=page_type,  # type: ignore[arg-type]
        title=title,
        meta_description=meta_description,
        canonical=canonical,
        is_noindex=is_noindex,
        hreflang_langs=hreflang_langs,
        h1s=h1s,
        h2s=h2s,
        image_count=image_count,
        images_missing_alt=images_missing_alt,
        has_schema_org=bool(schema_types),
        schema_types=list(dict.fromkeys(schema_types)),
        og_title=og_title,
        og_description=og_description,
        og_image=og_image,
        og_type=og_type,
        twitter_card=twitter_card,
        twitter_image=twitter_image,
        word_count_approx=word_count_approx,
        body_text_snippet=body_text_snippet,
        internal_links=internal_links,
        internal_link_anchors=internal_link_anchors,
        external_links=external_links,
        external_link_anchors=external_link_anchors,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_schema_types(obj: object, out: list[str]) -> None:
    if isinstance(obj, dict):
        t = obj.get("@type")
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, list):
            out.extend(str(x) for x in t if x)
        for v in obj.values():
            _collect_schema_types(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_schema_types(item, out)


# ---------------------------------------------------------------------------
# stdlib fallback (used if selectolax is not installed)
# ---------------------------------------------------------------------------

def _extract_signals_stdlib(html: str, url: str, page_type: str) -> PageSignals:
    """Minimal fallback extractor using stdlib html.parser.

    Less accurate than the selectolax path — anchor text and body snippet
    are not extracted. Used only when selectolax is unavailable.
    """
    from html.parser import HTMLParser

    base_netloc = urlparse(url).netloc

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.title = ""; self.meta_description = ""; self.canonical = ""
            self.is_noindex = False; self.og_title = ""; self.og_description = ""
            self.og_image = ""; self.og_type = ""; self.twitter_card = ""
            self.h1s: list[str] = []; self.h2s: list[str] = []
            self.image_count = 0; self.images_missing_alt = 0
            self.schema_types: list[str] = []
            self.internal_links: list[str] = []; self.external_links: list[str] = []
            self._body_parts: list[str] = []
            self._in_title = False; self._in_h1 = False; self._in_h2 = False
            self._in_body = False; self._in_script_ld = False; self._skip = 0

        def handle_starttag(self, tag, attrs):
            tag = tag.lower(); attr = dict(attrs)
            if tag in {"style", "noscript"}:
                self._skip += 1; return
            if tag == "script":
                if attr.get("type") == "application/ld+json":
                    self._in_script_ld = True
                else:
                    self._skip += 1
                return
            if tag == "body": self._in_body = True
            if tag == "title": self._in_title = True
            elif tag == "meta":
                name = (attr.get("name") or "").lower()
                prop = (attr.get("property") or "").lower()
                c = attr.get("content") or ""
                if name == "description": self.meta_description = c
                elif name == "robots" and "noindex" in c.lower(): self.is_noindex = True
                elif prop == "og:title": self.og_title = c
                elif prop == "og:description": self.og_description = c
                elif prop == "og:image": self.og_image = c
                elif prop == "og:type": self.og_type = c
                elif name == "twitter:card": self.twitter_card = c
            elif tag == "link":
                if (attr.get("rel") or "").lower() == "canonical":
                    self.canonical = attr.get("href") or ""
            elif tag == "h1": self._in_h1 = True
            elif tag == "h2": self._in_h2 = True
            elif tag == "img":
                self.image_count += 1
                if not (attr.get("alt") or "").strip(): self.images_missing_alt += 1
            elif tag == "a":
                href = attr.get("href") or ""
                if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                    full = urljoin(url, href)
                    netloc = urlparse(full).netloc
                    if netloc == base_netloc and len(self.internal_links) < 50:
                        self.internal_links.append(full)
                    elif netloc and len(self.external_links) < 20:
                        self.external_links.append(full)

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag in {"style", "noscript"}: self._skip = max(0, self._skip - 1)
            elif tag == "script":
                if self._in_script_ld: self._in_script_ld = False
                else: self._skip = max(0, self._skip - 1)
            elif tag == "title": self._in_title = False
            elif tag == "h1": self._in_h1 = False
            elif tag == "h2": self._in_h2 = False

        def handle_data(self, data):
            if self._in_script_ld:
                try:
                    _collect_schema_types(json.loads(data), self.schema_types)
                except Exception: pass
                return
            if self._skip: return
            if self._in_title: self.title = data.strip()
            if self._in_h1 and data.strip(): self.h1s.append(data.strip())
            if self._in_h2 and data.strip(): self.h2s.append(data.strip())
            if self._in_body and data.strip(): self._body_parts.append(data)

    p = _Parser()
    try:
        p.feed(html)
    except Exception:
        pass
    full_text = re.sub(r"\s+", " ", " ".join(p._body_parts)).strip()
    return PageSignals(
        url=url, page_type=page_type,  # type: ignore[arg-type]
        title=p.title, meta_description=p.meta_description, canonical=p.canonical,
        is_noindex=p.is_noindex, h1s=[h for h in p.h1s if h][:5],
        h2s=[h for h in p.h2s if h][:8],
        image_count=p.image_count, images_missing_alt=p.images_missing_alt,
        has_schema_org=bool(p.schema_types),
        schema_types=list(dict.fromkeys(p.schema_types)),
        og_title=p.og_title, og_description=p.og_description,
        og_image=p.og_image, og_type=p.og_type, twitter_card=p.twitter_card,
        word_count_approx=len(full_text.split()),
        body_text_snippet=full_text[:_BODY_SNIPPET_LEN],
        internal_links=list(dict.fromkeys(p.internal_links))[:50],
        external_links=list(dict.fromkeys(p.external_links))[:20],
    )
