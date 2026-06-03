"""HTML signal extractor for the SEO audit crawler.

Uses selectolax (Lexbor HTML5 engine — same parser Chrome uses) for fast,
browser-accurate parsing of real-world HTML.

Extracts per-page SEO signals:
  - Head: title, meta description, canonical, noindex, hreflang, AMP URL
  - OG/social: og:title/description/image/type, twitter:card/image
  - Structure: h1/h2 text, JSON-LD full objects + @types, microdata types (extruct)
  - Images: count + images missing alt, preload hints
  - Links: internal + external URLs with anchor text (parallel arrays)
  - Content: word count (trafilatura boilerplate removal), body text snippet
  - HTTP-level: X-Robots-Tag, Vary, Cache-Control (from response headers)
  - SPA detection: framework fingerprinting from static HTML markers
  - Noscript: visible fallback content for non-JS crawlers
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin, urlparse

from agents.audit.schema import PageSignals

logger = logging.getLogger(__name__)

_BODY_SNIPPET_LEN = 500
_MAX_INTERNAL_LINKS = 50
_MAX_EXTERNAL_LINKS = 20
_MAX_JSON_LD_OBJECTS = 10   # cap to avoid bloating the prompt

# SPA framework fingerprints detectable from static HTML alone.
# Order matters: most specific first.
_SPA_PATTERNS: list[tuple[str, str, str]] = [
    # (regex_pattern, framework_key, description)
    (r'<script[^>]+id=["\']__NEXT_DATA__["\']', "next_ssr",  "Next.js with SSR/SSG — content in static HTML"),
    (r'window\.__NEXT_DATA__',                   "next_ssr",  "Next.js with SSR/SSG — content in static HTML"),
    (r'<div[^>]+id=["\']__next["\'][^>]*>\s*</div>', "next_csr", "Next.js client-side only — empty shell"),
    (r'<div[^>]+id=["\']root["\'][^>]*>\s*</div>',   "react_csr","React client-side only — empty shell"),
    (r'<div[^>]+id=["\']app["\'][^>]*>\s*</div>',    "react_csr","React/Vue client-side only — empty shell"),
    (r'window\.__NUXT__',                            "nuxt",     "Nuxt.js"),
    (r'window\.gatsby',                              "gatsby",   "Gatsby"),
    (r'<div[^>]+id=["\']gatsby-focus-wrapper["\']',  "gatsby",   "Gatsby"),
]


def _get_text(node) -> str:
    if node is None:
        return ""
    return (node.text(deep=True, strip=True) or "").strip()


def _attr(node, name: str, default: str = "") -> str:
    if node is None:
        return default
    return (node.attributes.get(name) or default).strip()


def _detect_spa(html: str) -> tuple[bool, str]:
    """Return (is_spa_suspected, framework_key) by scanning static HTML markers."""
    for pattern, framework, _ in _SPA_PATTERNS:
        if re.search(pattern, html, re.IGNORECASE | re.DOTALL):
            # next_ssr means it IS server-rendered; not an SEO risk, but still label it
            return True, framework
    return False, ""


def _extract_microdata_types(html: str) -> list[str]:
    """Extract Schema.org types from HTML microdata (itemtype attributes).

    Tries extruct first for completeness; falls back to a regex scan.
    """
    types: list[str] = []
    try:
        import extruct
        data = extruct.extract(html, syntaxes=["microdata"], uniform=True)
        for item in data.get("microdata", []):
            t = item.get("type", "")
            if t:
                # Normalise schema.org URLs → bare type name
                types.append(t.rsplit("/", 1)[-1] if "/" in t else t)
    except Exception:
        # Regex fallback
        for m in re.finditer(r'itemtype=["\']https?://schema\.org/([^"\'>\s]+)', html, re.IGNORECASE):
            types.append(m.group(1))
    return list(dict.fromkeys(types))


def _extract_body_text(tree, html: str) -> tuple[int, str]:
    """Extract main body text using trafilatura for boilerplate removal.

    trafilatura uses ML-based content extraction (similar to what Google's
    content quality signals measure) — far more accurate than manual
    nav/footer/header CSS selector stripping for real-world pages.

    Falls back to the manual noise-stripping approach when trafilatura
    is unavailable or returns nothing.
    """
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,
        )
        if extracted and len(extracted.split()) > 10:
            word_count = len(extracted.split())
            snippet = extracted[:_BODY_SNIPPET_LEN]
            return word_count, snippet
    except Exception as exc:
        logger.debug("trafilatura extraction failed: %s", exc)

    # Manual fallback: strip known noise selectors then extract body text
    body = tree.css_first("body")
    if not body:
        return 0, ""
    for noise_sel in ("nav", "header", "footer", "script", "style", "noscript",
                      "[role='navigation']", "[role='banner']", "[role='contentinfo']"):
        for node in tree.css(noise_sel):
            node.decompose()
    full_text = re.sub(r"\s+", " ", body.text(deep=True, separator=" ", strip=True)).strip()
    return len(full_text.split()), full_text[:_BODY_SNIPPET_LEN]


def extract_signals(
    html: str,
    url: str,
    page_type: str = "other",
    response_headers: dict[str, str] | None = None,
) -> PageSignals:
    """Parse *html* and return a PageSignals instance for *url*.

    *response_headers* should be the lowercased HTTP response headers dict
    from FetchResult.headers — used to extract X-Robots-Tag, Vary, etc.
    """
    try:
        from selectolax.parser import HTMLParser as SParser
    except ImportError:
        logger.warning("selectolax not installed, falling back to stdlib html.parser")
        return _extract_signals_stdlib(html, url, page_type, response_headers)

    try:
        tree = SParser(html)
    except Exception as exc:
        logger.debug("selectolax parse error for %s: %s", url, exc)
        return PageSignals(url=url, page_type=page_type)  # type: ignore[arg-type]

    hdrs = response_headers or {}
    base_netloc = urlparse(url).netloc

    # ------------------------------------------------------------------
    # HTTP-level signals (from response headers)
    # ------------------------------------------------------------------
    x_robots_tag = hdrs.get("x-robots-tag", "")
    vary_header = hdrs.get("vary", "")
    cache_control = hdrs.get("cache-control", "")

    # ------------------------------------------------------------------
    # <head> signals
    # ------------------------------------------------------------------

    title = _get_text(tree.css_first("title"))

    meta_desc_node = tree.css_first('meta[name="description"]')
    meta_description = _attr(meta_desc_node, "content")

    canonical_node = tree.css_first('link[rel="canonical"]')
    canonical = _attr(canonical_node, "href")

    # noindex: <meta name="robots" content="noindex,..."> OR X-Robots-Tag header
    robots_node = tree.css_first('meta[name="robots"]')
    robots_content = _attr(robots_node, "content").lower()
    is_noindex = "noindex" in robots_content or "noindex" in x_robots_tag.lower()

    # hreflang: collect all lang values
    hreflang_langs = [
        _attr(node, "hreflang")
        for node in tree.css('link[rel="alternate"][hreflang]')
        if _attr(node, "hreflang")
    ]

    # AMP alternate
    amp_node = tree.css_first('link[rel="amphtml"]')
    amp_url = _attr(amp_node, "href")
    if amp_url:
        amp_url = urljoin(url, amp_url)

    # Preload hints
    preload_hints = len(tree.css('link[rel="preload"]'))

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
    # JSON-LD structured data — full objects + type list
    # ------------------------------------------------------------------

    schema_types: list[str] = []
    schema_json_ld: list[dict] = []
    for script in tree.css('script[type="application/ld+json"]'):
        raw = script.text(strip=True)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            if len(schema_json_ld) < _MAX_JSON_LD_OBJECTS:
                schema_json_ld.append(obj if isinstance(obj, dict) else {"@graph": obj})
            _collect_schema_types(obj, schema_types)
        except (json.JSONDecodeError, ValueError):
            pass

    # ------------------------------------------------------------------
    # Microdata types (extruct / regex)
    # ------------------------------------------------------------------
    microdata_types = _extract_microdata_types(html)

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
    # Noscript content — what non-JS crawlers see as fallback
    # ------------------------------------------------------------------
    noscript_parts = []
    for ns in tree.css("noscript"):
        t = _get_text(ns)
        if t:
            noscript_parts.append(t)
    noscript_content = " ".join(noscript_parts)[:500]

    # ------------------------------------------------------------------
    # SPA detection
    # ------------------------------------------------------------------
    is_spa_suspected, spa_framework = _detect_spa(html)

    # ------------------------------------------------------------------
    # Body text: word count + snippet via trafilatura
    # ------------------------------------------------------------------
    word_count_approx, body_text_snippet = _extract_body_text(tree, html)

    return PageSignals(
        url=url,
        page_type=page_type,  # type: ignore[arg-type]
        title=title,
        meta_description=meta_description,
        canonical=canonical,
        is_noindex=is_noindex,
        hreflang_langs=hreflang_langs,
        amp_url=amp_url,
        preload_hints=preload_hints,
        h1s=h1s,
        h2s=h2s,
        image_count=image_count,
        images_missing_alt=images_missing_alt,
        has_schema_org=bool(schema_types) or bool(microdata_types),
        schema_types=list(dict.fromkeys(schema_types)),
        schema_json_ld=schema_json_ld,
        microdata_types=list(dict.fromkeys(microdata_types)),
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
        noscript_content=noscript_content,
        is_spa_suspected=is_spa_suspected,
        spa_framework=spa_framework,
        x_robots_tag=x_robots_tag,
        vary_header=vary_header,
        cache_control=cache_control,
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

def _extract_signals_stdlib(
    html: str,
    url: str,
    page_type: str,
    response_headers: dict[str, str] | None = None,
) -> PageSignals:
    """Minimal fallback extractor using stdlib html.parser."""
    from html.parser import HTMLParser

    hdrs = response_headers or {}
    x_robots_tag = hdrs.get("x-robots-tag", "")
    vary_header = hdrs.get("vary", "")
    cache_control = hdrs.get("cache-control", "")

    base_netloc = urlparse(url).netloc
    is_spa_suspected, spa_framework = _detect_spa(html)
    microdata_types = _extract_microdata_types(html)
    amp_match = re.search(r'<link[^>]+rel=["\']amphtml["\'][^>]+href=["\']([^"\']+)', html, re.IGNORECASE)
    amp_url = urljoin(url, amp_match.group(1)) if amp_match else ""
    preload_hints = len(re.findall(r'<link[^>]+rel=["\']preload["\']', html, re.IGNORECASE))
    noscript_texts = re.findall(r'<noscript[^>]*>(.*?)</noscript>', html, re.IGNORECASE | re.DOTALL)
    noscript_content = " ".join(re.sub(r'<[^>]+>', '', t).strip() for t in noscript_texts)[:500]

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.title = ""
            self.meta_description = ""
            self.canonical = ""
            self.is_noindex = False
            self.og_title = ""
            self.og_description = ""
            self.og_image = ""
            self.og_type = ""
            self.twitter_card = ""
            self.h1s: list[str] = []
            self.h2s: list[str] = []
            self.image_count = 0
            self.images_missing_alt = 0
            self.schema_types: list[str] = []
            self.schema_json_ld: list[dict] = []
            self.internal_links: list[str] = []
            self.external_links: list[str] = []
            self._body_parts: list[str] = []
            self._in_title = False
            self._in_h1 = False
            self._in_h2 = False
            self._in_body = False
            self._in_script_ld = False
            self._skip = 0

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            attr = dict(attrs)
            if tag in {"style", "noscript"}:
                self._skip += 1
                return
            if tag == "script":
                if attr.get("type") == "application/ld+json":
                    self._in_script_ld = True
                else:
                    self._skip += 1
                return
            if tag == "body":
                self._in_body = True
            if tag == "title":
                self._in_title = True
            elif tag == "meta":
                name = (attr.get("name") or "").lower()
                prop = (attr.get("property") or "").lower()
                c = attr.get("content") or ""
                if name == "description":
                    self.meta_description = c
                elif name == "robots" and "noindex" in c.lower():
                    self.is_noindex = True
                elif prop == "og:title":
                    self.og_title = c
                elif prop == "og:description":
                    self.og_description = c
                elif prop == "og:image":
                    self.og_image = c
                elif prop == "og:type":
                    self.og_type = c
                elif name == "twitter:card":
                    self.twitter_card = c
            elif tag == "link":
                rel = (attr.get("rel") or "").lower()
                if rel == "canonical":
                    self.canonical = attr.get("href") or ""
            elif tag == "h1":
                self._in_h1 = True
            elif tag == "h2":
                self._in_h2 = True
            elif tag == "img":
                self.image_count += 1
                if not (attr.get("alt") or "").strip():
                    self.images_missing_alt += 1
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
            if tag in {"style", "noscript"}:
                self._skip = max(0, self._skip - 1)
            elif tag == "script":
                if self._in_script_ld:
                    self._in_script_ld = False
                else:
                    self._skip = max(0, self._skip - 1)
            elif tag == "title":
                self._in_title = False
            elif tag == "h1":
                self._in_h1 = False
            elif tag == "h2":
                self._in_h2 = False

        def handle_data(self, data):
            if self._in_script_ld:
                try:
                    obj = json.loads(data)
                    _collect_schema_types(obj, self.schema_types)
                    if len(self.schema_json_ld) < _MAX_JSON_LD_OBJECTS:
                        self.schema_json_ld.append(obj if isinstance(obj, dict) else {"@graph": obj})
                except Exception:
                    pass
                return
            if self._skip:
                return
            if self._in_title:
                self.title = data.strip()
            if self._in_h1 and data.strip():
                self.h1s.append(data.strip())
            if self._in_h2 and data.strip():
                self.h2s.append(data.strip())
            if self._in_body and data.strip():
                self._body_parts.append(data)

    p = _Parser()
    try:
        p.feed(html)
    except Exception:
        pass

    is_noindex_combined = p.is_noindex or "noindex" in x_robots_tag.lower()
    full_text = re.sub(r"\s+", " ", " ".join(p._body_parts)).strip()

    return PageSignals(
        url=url, page_type=page_type,  # type: ignore[arg-type]
        title=p.title, meta_description=p.meta_description, canonical=p.canonical,
        is_noindex=is_noindex_combined,
        h1s=[h for h in p.h1s if h][:5],
        h2s=[h for h in p.h2s if h][:8],
        image_count=p.image_count, images_missing_alt=p.images_missing_alt,
        has_schema_org=bool(p.schema_types) or bool(microdata_types),
        schema_types=list(dict.fromkeys(p.schema_types)),
        schema_json_ld=p.schema_json_ld,
        microdata_types=list(dict.fromkeys(microdata_types)),
        og_title=p.og_title, og_description=p.og_description,
        og_image=p.og_image, og_type=p.og_type, twitter_card=p.twitter_card,
        word_count_approx=len(full_text.split()),
        body_text_snippet=full_text[:_BODY_SNIPPET_LEN],
        internal_links=list(dict.fromkeys(p.internal_links))[:50],
        external_links=list(dict.fromkeys(p.external_links))[:20],
        amp_url=amp_url,
        preload_hints=preload_hints,
        noscript_content=noscript_content,
        is_spa_suspected=is_spa_suspected,
        spa_framework=spa_framework,
        x_robots_tag=x_robots_tag,
        vary_header=vary_header,
        cache_control=cache_control,
    )
