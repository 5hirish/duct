#!/usr/bin/env python3
"""Generate the translated marketing site from the English pages, one PO per language.

    python3 scripts/build_site_i18n.py            # extract → site/i18n/<lang>.po, render → site/<prefix>/
    python3 scripts/build_site_i18n.py --check    # CI: generated pages current, nothing untranslated
    python3 scripts/build_site_i18n.py --extract  # catalogues only, no rendering

The English pages under ``site/`` stay hand-written and stay the source of
truth; this reads them the way ``build_blog.py`` reads a post. Every run of
text a person reads becomes one catalogue entry — a sentence with its inline
markup kept together as ``<0>…</0>`` placeholders, so a translator can move the
link to where the grammar puts it — plus the attributes people read (``alt``,
``title``, ``placeholder``, the meta descriptions) and the strings the site's
own JavaScript injects (wrapped in ``ductT('…')`` in ``assets/*.js``).

Then it writes ``site/es/about.html`` and friends: same markup, translated
text, ``<html lang>`` set, canonical and ``og:url`` pointing at the localised
address, an hreflang block for every language with the matching ``og:locale``
pair, relative asset paths made root-absolute (a page under ``/es/`` cannot
use ``assets/duct.css``), internal links pointed at their localised twin, the
JSON-LD translated with its addresses localised and ``inLanguage`` set, and a
``window.DUCT_I18N`` dictionary for the JavaScript strings. The English pages
get the same hreflang block, between markers, so both directions of the
alternate link exist.

A missing translation renders as English rather than a hole, and ``--check``
fails on it, because a page that silently ships half-English is the failure
this whole setup exists to prevent. ``scripts/i18n/fill.py`` is what fills it.

Why not templates: twelve hand-written pages with no build step is the site's
contract (site/AGENTS.md), and it holds — the English files are untouched
apart from the marked hreflang block. What is generated is generated, like
the blog, and never edited by hand.
"""

from __future__ import annotations

import argparse
import html
import json
import posixpath
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "i18n"))
import po  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CATALOG_DIR = SITE / "i18n"
BASE_URL = "https://getduct.ai"

#: URL prefix → language tag. The prefix is lowercase because URLs are; the
#: tag is what `lang` and `hreflang` carry. Adding a language is one line here
#: and a fill run.
LOCALES: dict[str, str] = {"es": "es", "pt-br": "pt-BR", "de": "de", "ja": "ja"}

#: What gets translated. Blog and changelog are deliberately out: the blog is
#: long-form content whose translation is a content decision, and the
#: changelog is a record.
SOURCE_GLOBS = ("*.html", "tools/*.html", "partials/*.html")
EXCLUDE = {"404.html"}  # Pages serves one 404 for every miss, so a localised copy is unreachable
JS_SOURCES = ("assets/duct.js", "assets/duct-download.js", "assets/tool-validation.js")

INLINE = {
    "a", "abbr", "b", "bdi", "bdo", "br", "cite", "code", "data", "dfn", "em", "i", "kbd",
    "mark", "q", "s", "samp", "small", "span", "strong", "sub", "sup", "time", "u", "var",
    "wbr", "img", "svg",
}
VOID = {"br", "wbr", "img", "input", "meta", "link", "hr", "source", "track", "area", "base", "col", "embed", "param"}
#: Whole subtrees that never hold copy (or hold copy nobody translates).
SKIP = {"script", "style", "noscript", "template", "pre", "iframe", "textarea", "svg"}
COPY_ATTRS = {"alt", "title", "aria-label", "aria-description", "placeholder", "label"}
META_NAMES = {"description", "twitter:title", "twitter:description"}
META_PROPS = {"og:title", "og:description"}
URL_ATTRS = {"href", "src", "poster", "data-src", "data-duct-partial"}

#: JSON-LD. The FAQ, breadcrumb and application blocks carry the same copy as
#: the page, and Google reads them as claims about *this* page: a German page
#: whose FAQPage is in English contradicts its own text, and a WebApplication
#: whose `url` is the English address tells the crawler the page is a copy.
#: So a string under one of these keys is translated like a text run, an
#: address under one of these keys is localised like an href, and every
#: top-level object states its `inLanguage`.
LD_COPY_KEYS = {"name", "headline", "alternativeHeadline", "description", "text", "alternateName", "caption"}
LD_URL_KEYS = {"url", "mainEntityOfPage", "@id", "item"}
#: Objects that name a person or an organisation: their `name` is a name, and
#: an entity has no language.
LD_ENTITY_TYPES = {"Person", "Organization", "ContactPoint", "Brand"}
#: What `og:locale` carries for each language tag. Facebook and LinkedIn key
#: on this, not on `<html lang>`.
OG_LOCALES = {"en": "en_US", "es": "es_ES", "pt-BR": "pt_BR", "de": "de_DE", "ja": "ja_JP"}

#: Attribute value that is a name, a number or a symbol, not copy.
NAMES = {
    "Duct", "GitHub", "Google", "Stripe", "MIT", "OK", "GA4", "GSC", "GTM", "SEO", "ROAS", "CPA",
    "CPC", "CPM", "CTR", "LTV", "CAC", "MRR", "macOS", "Windows", "Linux", "X", "→", "↓", "·", "—",
    # A language's own name is never translated: someone who landed in the
    # wrong language has to be able to find theirs in the list.
    "English", "Español", "Português", "Português (Brasil)", "Deutsch", "日本語", "Language",
}
LETTERS = re.compile(r"\p{L}" if False else r"[^\W\d_]{2,}")
HREFLANG_START = "<!-- hreflang:start -->"
HREFLANG_END = "<!-- hreflang:end -->"
JS_MARK = "<!-- i18n:js -->"


def is_copy(text: str) -> bool:
    t = " ".join(text.split())
    if not t or not LETTERS.search(t):
        return False
    if t in NAMES:
        return False
    # "e.g. 9000" is a placeholder people read; "01", "v0.7.0", "→" are not.
    return True


# ---------------------------------------------------------------------------
# Page model: a token stream we can re-emit byte for byte, with the text runs
# a person reads grouped into segments.
# ---------------------------------------------------------------------------

@dataclass
class Tok:
    kind: str          # text | open | close | void | raw
    raw: str = ""      # what to emit when untouched
    tag: str = ""
    attrs: list[tuple[str, str | None]] = field(default_factory=list)


@dataclass
class Segment:
    """A run of text and inline tags between two block boundaries."""
    tokens: list[Tok]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[object] = []      # Tok or Segment
        self.seg: list[Tok] = []
        self.skip: list[str] = []        # open SKIP tags
        self.opaque: list[str] = []      # raw pieces while inside <svg>

    # -- helpers ---------------------------------------------------------------
    def _flush(self) -> None:
        if self.seg:
            self.out.append(Segment(self.seg))
            self.seg = []

    def _emit(self, tok: Tok, inline: bool) -> None:
        if self.opaque:
            self.opaque.append(tok.raw)
            return
        if inline:
            self.seg.append(tok)
        else:
            self._flush()
            self.out.append(tok)

    # -- events ----------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        if tag == "svg" and not self.skip:
            self.opaque.append(raw)
            self.skip.append(tag)
            return
        if self.opaque:
            self.opaque.append(raw)
            if tag in SKIP:
                self.skip.append(tag)
            return
        if tag in SKIP:
            self.skip.append(tag)
        tok = Tok("void" if tag in VOID else "open", raw, tag, list(attrs))
        self._emit(tok, tag in INLINE and not self.skip)

    def handle_startendtag(self, tag, attrs):
        raw = self.get_starttag_text() or ""
        if tag == "svg" and not self.skip:
            # <svg/> is a void here; treat as opaque inline token
            self._emit(Tok("void", raw, tag, list(attrs)), True)
            return
        if self.opaque:
            self.opaque.append(raw)
            return
        self._emit(Tok("void", raw, tag, list(attrs)), tag in INLINE and not self.skip)

    def handle_endtag(self, tag):
        raw = f"</{tag}>"
        if self.opaque:
            self.opaque.append(raw)
            if self.skip and self.skip[-1] == tag:
                self.skip.pop()
                if tag == "svg" and not any(t == "svg" for t in self.skip):
                    whole = "".join(self.opaque)
                    self.opaque = []
                    self._emit(Tok("void", whole, "svg"), not self.skip)
            return
        if self.skip and self.skip[-1] == tag:
            self.skip.pop()
        if tag in VOID:
            return
        self._emit(Tok("close", raw, tag), tag in INLINE and not self.skip)

    def handle_data(self, data):
        if self.opaque:
            self.opaque.append(data)
            return
        if self.skip:
            self._flush()
            self.out.append(Tok("raw", data))
            return
        self.seg.append(Tok("text", data))

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")

    def handle_comment(self, data):
        self._emit(Tok("raw", f"<!--{data}-->"), False)

    def handle_decl(self, decl):
        self._emit(Tok("raw", f"<!{decl}>"), False)

    def handle_pi(self, data):
        self._emit(Tok("raw", f"<?{data}>"), False)

    def unknown_decl(self, data):
        self._emit(Tok("raw", f"<![{data}]>"), False)

    def close(self):
        super().close()
        self._flush()


def parse_page(text: str) -> list[object]:
    p = PageParser()
    p.feed(text)
    p.close()
    return p.out


# ---------------------------------------------------------------------------
# Segments → messages and back
# ---------------------------------------------------------------------------

_WS = re.compile(r"\s+")


def _text_of(tokens: list[Tok]) -> str:
    return "".join(t.raw for t in tokens if t.kind == "text")


def _trim(tokens: list[Tok]) -> tuple[str, list[Tok], str]:
    """Split leading/trailing whitespace off, so indentation survives untouched."""
    lead = tail = ""
    toks = list(tokens)
    if toks and toks[0].kind == "text":
        stripped = toks[0].raw.lstrip()
        lead = toks[0].raw[: len(toks[0].raw) - len(stripped)]
        if stripped:
            toks[0] = Tok("text", stripped)
        else:
            toks.pop(0)
    if toks and toks[-1].kind == "text":
        stripped = toks[-1].raw.rstrip()
        tail = toks[-1].raw[len(stripped):]
        if stripped:
            toks[-1] = Tok("text", stripped)
        else:
            toks.pop()
    return lead, toks, tail


def _unwrap(tokens: list[Tok]) -> tuple[list[Tok], list[Tok], list[Tok]]:
    """<a class=btn>Download</a> alone in a block: the link is not the message."""
    prefix: list[Tok] = []
    suffix: list[Tok] = []
    toks = tokens
    while len(toks) >= 2 and toks[0].kind == "open" and toks[-1].kind == "close" and toks[0].tag == toks[-1].tag:
        depth = 0
        wraps = True
        for i, t in enumerate(toks):
            if t.kind == "open":
                depth += 1
            elif t.kind == "close":
                depth -= 1
            if depth == 0 and i < len(toks) - 1:
                wraps = False
                break
        if not wraps:
            break
        prefix.append(toks[0])
        suffix.insert(0, toks[-1])
        lead, inner, tail = _trim(toks[1:-1])
        if lead:
            prefix.append(Tok("text", lead))
        if tail:
            suffix.insert(0, Tok("text", tail))
        toks = inner
    return prefix, toks, suffix


def build_message(tokens: list[Tok]) -> tuple[str, dict[str, str]]:
    """The msgid with inline tags as <n>…</n> placeholders, and how to put them back."""
    parts: list[str] = []
    mapping: dict[str, str] = {}
    stack: list[int] = []
    n = 0
    for t in tokens:
        if t.kind == "text":
            parts.append(html.unescape(t.raw))
        elif t.kind == "open":
            parts.append(f"<{n}>")
            mapping[f"<{n}>"] = t.raw
            stack.append(n)
            n += 1
        elif t.kind == "close":
            k = stack.pop() if stack else n
            parts.append(f"</{k}>")
            mapping[f"</{k}>"] = t.raw
        else:  # void / opaque
            parts.append(f"<{n}/>")
            mapping[f"<{n}/>"] = t.raw
            n += 1
    msgid = _WS.sub(" ", "".join(parts)).strip()
    return msgid, mapping


_PLACEHOLDER = re.compile(r"</?\d+/?>")


def render_message(msgstr: str, mapping: dict[str, str]) -> str | None:
    if sorted(_PLACEHOLDER.findall(msgstr)) != sorted(mapping):
        return None
    out: list[str] = []
    pos = 0
    for m in _PLACEHOLDER.finditer(msgstr):
        out.append(html.escape(msgstr[pos:m.start()], quote=False))
        out.append(mapping[m.group(0)])
        pos = m.end()
    out.append(html.escape(msgstr[pos:], quote=False))
    return "".join(out)


# ---------------------------------------------------------------------------
# One pass over a page, in extract or render mode
# ---------------------------------------------------------------------------

class Translator:
    """extract: records what it sees. render: answers from a catalogue."""

    def __init__(self, catalog: po.Catalog | None, page: str) -> None:
        self.catalog = catalog
        self.page = page
        self.seen: dict[tuple[str | None, str], tuple[set[str], set[str]]] = {}
        self.missing: list[str] = []

    def __call__(self, msgid: str, note: str = "", ctx: str | None = None) -> str | None:
        refs, notes = self.seen.setdefault((ctx, msgid), (set(), set()))
        refs.add(self.page)
        if note:
            notes.add(note)
        if self.catalog is None:
            return None
        entry = self.catalog.find(msgid, ctx)
        if entry is None or not entry.msgstr or entry.obsolete:
            self.missing.append(msgid)
            return None
        return entry.msgstr


def _attr_str(attrs: list[tuple[str, str | None]]) -> str:
    bits = []
    for k, v in attrs:
        bits.append(k if v is None else f'{k}="{html.escape(v, quote=True)}"')
    return (" " + " ".join(bits)) if bits else ""


@dataclass
class PageContext:
    rel: str                       # "about.html", "tools/cpa-calculator.html", "partials/nav-home.html"
    prefix: str | None = None      # "es" when rendering, None for extraction/English
    lang: str = "en"
    localized_paths: set[str] = field(default_factory=set)   # "/about", "/tools/", ...
    js_strings: dict[str, str] = field(default_factory=dict)

    @property
    def url_path(self) -> str:
        """The page's own clean path: about.html → /about, tools/index.html → /tools/."""
        p = "/" + self.rel
        if p.endswith("/index.html"):
            return p[: -len("index.html")]
        if p.endswith(".html"):
            return p[:-5]
        return p

    @property
    def dir_url(self) -> str:
        d = posixpath.dirname("/" + self.rel)
        # dirname("/about.html") is "/" already; appending another slash made
        # every root page's stylesheet protocol-relative ("//assets/duct.css").
        return d if d.endswith("/") else d + "/"


def localize_path(path: str, ctx: PageContext) -> str:
    """A root-absolute internal path → its localised twin, when one exists."""
    if ctx.prefix is None:
        return path
    m = re.match(r"^([^?#]*)(.*)$", path)
    clean, rest = m.group(1), m.group(2)
    if clean.startswith("/partials/"):
        return f"/{ctx.prefix}{clean}{rest}"
    if clean in ctx.localized_paths:
        return f"/{ctx.prefix}{clean}{rest}"
    return path


def rewrite_url(value: str, attr: str, ctx: PageContext) -> str:
    if ctx.prefix is None:
        return value
    v = value.strip()
    if not v or re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|#|\?)", v, re.I):
        return value
    if attr == "srcset":
        return ", ".join(
            " ".join([rewrite_url(part.split()[0], "src", ctx), *part.split()[1:]])
            for part in v.split(",")
        )
    if not v.startswith("/"):
        v = posixpath.normpath(posixpath.join(ctx.dir_url, v))
        if value.strip().endswith("/") and not v.endswith("/"):
            v += "/"
    return localize_path(v, ctx)


def transform(text: str, tr: Translator, ctx: PageContext) -> str:
    nodes = parse_page(text)
    out: list[str] = []
    in_ld = False
    for node in nodes:
        if isinstance(node, Segment):
            out.append(_render_segment(node, tr, ctx))
            continue
        if node.kind == "raw" and in_ld:
            out.append(_render_ld(node.raw, tr, ctx))
            continue
        if node.tag == "script":
            in_ld = node.kind == "open" and dict(node.attrs).get("type", "").lower() == "application/ld+json"
        out.append(_render_tok(node, tr, ctx))
    return "".join(out)


# ---------------------------------------------------------------------------
# JSON-LD: the structured data says in its own language what the page says
# ---------------------------------------------------------------------------

def _localize_ld(data, tr: Translator, ctx: PageContext):
    if isinstance(data, list):
        return [_localize_ld(x, tr, ctx) for x in data]
    if not isinstance(data, dict):
        return data
    is_entity = data.get("@type") in LD_ENTITY_TYPES
    out = {}
    for k, v in data.items():
        if isinstance(v, str):
            if k in LD_URL_KEYS and ctx.prefix is not None and v.startswith(BASE_URL):
                path = v[len(BASE_URL):]
                if path in ctx.localized_paths:
                    v = BASE_URL + localize_path(path, ctx)
            elif k in LD_COPY_KEYS and not is_entity and is_copy(v):
                got = tr(_WS.sub(" ", v).strip())
                if got is not None:
                    v = got
        else:
            v = _localize_ld(v, tr, ctx)
        out[k] = v
    return out


def _with_language(obj: dict, lang: str) -> dict:
    """`inLanguage` right after `@type`, replacing whatever the English block said."""
    out = {}
    for k, v in obj.items():
        if k == "inLanguage":
            continue
        out[k] = v
        if k == "@type":
            out["inLanguage"] = lang
    out.setdefault("inLanguage", lang)
    return out


def _render_ld(raw: str, tr: Translator, ctx: PageContext) -> str:
    body = raw.strip()
    if not body:
        return raw
    try:
        data = json.loads(body)
    except ValueError:
        return raw  # check-pages.py reports it; a broken block is not ours to guess at
    data = _localize_ld(data, tr, ctx)
    if ctx.prefix is None:
        return raw  # extraction: recorded, unchanged
    if isinstance(data, list):
        data = [_with_language(o, ctx.lang) if isinstance(o, dict) and o.get("@type") not in LD_ENTITY_TYPES else o for o in data]
    elif data.get("@type") not in LD_ENTITY_TYPES:
        data = _with_language(data, ctx.lang)
    pretty = "\n" in body
    text = json.dumps(data, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":"))
    # "</" inside a script element ends it early in every browser.
    text = text.replace("</", "<\\/")
    lead = raw[: len(raw) - len(raw.lstrip())]
    tail = raw[len(raw.rstrip()):]
    return lead + text + tail


def _render_tok(t: Tok, tr: Translator, ctx: PageContext) -> str:
    if t.kind not in ("open", "void"):
        return t.raw
    attrs = list(t.attrs)
    changed = False
    is_meta = t.tag == "meta"
    meta_key = ""
    if is_meta:
        d = dict(attrs)
        if d.get("name") in META_NAMES:
            meta_key = d["name"]
        elif d.get("property") in META_PROPS:
            meta_key = d["property"]
    for i, (k, v) in enumerate(attrs):
        if v is None:
            continue
        if (k in COPY_ATTRS and t.tag != "iframe") or (is_meta and k == "content" and meta_key) or (
            t.tag == "input" and k == "value" and dict(attrs).get("type") in ("submit", "button", "reset")
        ):
            if is_copy(v):
                note = f"{t.tag} {k}" if not meta_key else f"meta {meta_key}"
                msg = _WS.sub(" ", v).strip()
                got = tr(msg, note)
                if got is not None and got != v:
                    attrs[i] = (k, got)
                    changed = True
        if k in URL_ATTRS or k == "srcset":
            new = rewrite_url(v, k, ctx)
            if new != v:
                attrs[i] = (k, new)
                changed = True
    if t.tag == "html" and ctx.prefix is not None:
        attrs = [(k, ctx.lang if k == "lang" else v) for k, v in attrs]
        changed = True
    if t.tag == "meta" and meta_key == "" and ctx.prefix is not None and dict(attrs).get("property") == "og:url":
        attrs = [(k, BASE_URL + localize_path(ctx.url_path, ctx) if k == "content" else v) for k, v in attrs]
        changed = True
    if t.tag == "link" and ctx.prefix is not None and dict(attrs).get("rel") == "canonical":
        attrs = [(k, BASE_URL + localize_path(ctx.url_path, ctx) if k == "href" else v) for k, v in attrs]
        changed = True
    if not changed:
        return t.raw
    close = "/" if t.raw.rstrip().endswith("/>") else ""
    return f"<{t.tag}{_attr_str(attrs)}{close}>"


def _split_items(tokens: list[Tok]) -> list[list[Tok]] | None:
    """Sibling links in one block are separate messages, not one.

    `<a>About</a> <a>Privacy</a> <a>Terms</a>` shares a block but no sentence.
    When every depth-0 text token is whitespace and there are at least two
    top-level items, each item is its own segment. A sentence with a link in it
    has depth-0 words and stays whole.
    """
    items: list[list[Tok]] = []
    depth = 0
    current: list[Tok] = []
    for t in tokens:
        if depth == 0 and t.kind == "text":
            if t.raw.strip():
                return None
            if current:
                items.append(current)
                current = []
            items.append([t])
            continue
        current.append(t)
        if t.kind == "open":
            depth += 1
        elif t.kind == "close":
            depth -= 1
            if depth == 0:
                items.append(current)
                current = []
        elif t.kind == "void" and depth == 0:
            items.append(current)
            current = []
    if current:
        items.append(current)
    real = [i for i in items if not (len(i) == 1 and i[0].kind == "text")]
    return items if len(real) >= 2 else None


def _render_segment(seg: Segment, tr: Translator, ctx: PageContext) -> str:
    lead, toks, tail = _trim(seg.tokens)
    items = _split_items(toks)
    if items is not None:
        return lead + "".join(
            item[0].raw if len(item) == 1 and item[0].kind == "text" else _render_segment(Segment(item), tr, ctx)
            for item in items
        ) + tail
    prefix, inner, suffix = _unwrap(toks)
    rendered_prefix = "".join(_render_tok(t, tr, ctx) if t.kind != "text" else t.raw for t in prefix)
    rendered_suffix = "".join(_render_tok(t, tr, ctx) if t.kind != "text" else t.raw for t in suffix)
    if not is_copy(html.unescape(_text_of(inner))):
        body = "".join(_render_tok(t, tr, ctx) if t.kind != "text" else t.raw for t in inner)
        return lead + rendered_prefix + body + rendered_suffix + tail
    # Inline tags inside the message still get their own attributes and URLs
    # rewritten (an <a href="/about"> in a sentence, an <img alt>).
    inner = [Tok(t.kind, _render_tok(t, tr, ctx), t.tag, t.attrs) if t.kind != "text" else t for t in inner]
    msgid, mapping = build_message(inner)
    got = tr(msgid)
    if got is None:
        body = "".join(t.raw for t in inner)
    else:
        body = render_message(got, mapping)
        if body is None:
            print(f"  placeholder mismatch, kept English: {msgid[:60]!r}", file=sys.stderr)
            body = "".join(t.raw for t in inner)
    return lead + rendered_prefix + body + rendered_suffix + tail


# ---------------------------------------------------------------------------
# JavaScript strings: t('…') in assets/*.js
# ---------------------------------------------------------------------------

_JS_T = re.compile(r"""\bductT\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*\)""")


def js_strings() -> list[str]:
    found: list[str] = []
    for rel in JS_SOURCES:
        src = (SITE / rel).read_text(encoding="utf-8")
        for m in _JS_T.finditer(src):
            s = (m.group(1) if m.group(1) is not None else m.group(2))
            s = s.encode().decode("unicode_escape") if "\\" in s else s
            if s not in found:
                found.append(s)
    return found


# ---------------------------------------------------------------------------
# Head blocks: hreflang, and the JS dictionary
# ---------------------------------------------------------------------------

def hreflang_block(url_path: str, lang: str = "en") -> str:
    """Every language's address for this page, then the OG locale and its alternates.

    The `og:locale` lines live in the same marked block because they are the
    same fact for a different reader: hreflang is for search engines, the OG
    pair is for the share cards Facebook and LinkedIn draw.
    """
    lines = [HREFLANG_START]
    lines.append(f'<link rel="alternate" hreflang="x-default" href="{BASE_URL}{url_path}"/>')
    lines.append(f'<link rel="alternate" hreflang="en" href="{BASE_URL}{url_path}"/>')
    for prefix, tag in LOCALES.items():
        lines.append(f'<link rel="alternate" hreflang="{tag}" href="{BASE_URL}/{prefix}{url_path}"/>')
    lines.append(f'<meta property="og:locale" content="{OG_LOCALES[lang]}"/>')
    for tag, code in OG_LOCALES.items():
        if tag != lang:
            lines.append(f'<meta property="og:locale:alternate" content="{code}"/>')
    lines.append(HREFLANG_END)
    return "\n".join(lines)


_CANONICAL = re.compile(r'<link rel="canonical" href="[^"]*"\s*/?>')
_HREFLANG_OLD = re.compile(re.escape(HREFLANG_START) + r".*?" + re.escape(HREFLANG_END) + r"\n?", re.S)


def with_hreflang(text: str, url_path: str, lang: str = "en") -> str:
    text = _HREFLANG_OLD.sub("", text)
    m = _CANONICAL.search(text)
    if not m:
        return text
    return text[: m.end()] + "\n" + hreflang_block(url_path, lang) + text[m.end():]


_CONFIG_SCRIPT = re.compile(r'<script src="(?:\.\./|/)?assets/config\.js"')


def with_js_dictionary(text: str, strings: dict[str, str]) -> str:
    if not strings:
        return text
    payload = json.dumps(strings, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tag = f"{JS_MARK}<script>window.DUCT_I18N={payload};</script>\n"
    m = _CONFIG_SCRIPT.search(text)
    if not m:
        return text
    return text[: m.start()] + tag + text[m.start():]


def select_current(text: str, prefix: str) -> str:
    """Mark the current language in every [data-duct-lang] select."""
    def fix(m: re.Match) -> str:
        block = m.group(0)
        block = re.sub(r'(<option value="[^"]*")\s+selected', r"\1", block)
        return re.sub(rf'(<option value="{re.escape(prefix)}")', r"\1 selected", block)
    return re.sub(r"<select[^>]*data-duct-lang[^>]*>.*?</select>", fix, text, flags=re.S)


# ---------------------------------------------------------------------------
# Catalogues
# ---------------------------------------------------------------------------

def source_pages() -> list[str]:
    rels: list[str] = []
    for pattern in SOURCE_GLOBS:
        for path in sorted(SITE.glob(pattern)):
            rel = path.relative_to(SITE).as_posix()
            if rel not in EXCLUDE:
                rels.append(rel)
    return rels


def localized_paths(pages: list[str]) -> set[str]:
    out = set()
    for rel in pages:
        if rel.startswith("partials/"):
            continue
        out.add(PageContext(rel).url_path)
    return out


def extract() -> dict[tuple[str | None, str], tuple[set[str], set[str]]]:
    pages = source_pages()
    seen: dict[tuple[str | None, str], tuple[set[str], set[str]]] = {}
    for rel in pages:
        tr = Translator(None, rel)
        transform((SITE / rel).read_text(encoding="utf-8"), tr, PageContext(rel))
        for key, (refs, notes) in tr.seen.items():
            r, n = seen.setdefault(key, (set(), set()))
            r |= refs
            n |= notes
    for s in js_strings():
        r, n = seen.setdefault(("js", s), (set(), set()))
        r.add("assets/*.js")
    return seen


def merge_catalog(path: Path, lang: str, seen) -> tuple[po.Catalog, int]:
    old = po.load(path) if path.exists() else po.Catalog()
    known = {e.key: e for e in old.entries if not e.is_header}
    header = old.header or po.Entry(msgid="", msgstr=(
        "MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n"
        f"Content-Transfer-Encoding: 8bit\nLanguage: {lang}\nX-Generator: build_site_i18n.py\n"
    ))
    entries = [header]
    keys = sorted(seen, key=lambda k: (sorted(seen[k][0])[0], k[1]))
    for key in keys:
        ctx, msgid = key
        refs, notes = seen[key]
        prev = known.pop(key, None)
        entries.append(po.Entry(
            msgid=msgid,
            msgstr=prev.msgstr if prev and not prev.obsolete else "",
            msgctxt=ctx,
            extracted_comments=sorted(notes),
            references=sorted(refs),
            flags=[],
        ))
    # Strings that left the pages keep their translation, marked obsolete, so a
    # sentence that comes back after an edit does not get translated twice.
    for prev in known.values():
        if prev.msgstr:
            prev.obsolete = True
            prev.references = []
            entries.append(prev)
    catalog = po.Catalog(entries)
    return catalog, len(catalog.untranslated())


def write_catalogs(seen) -> dict[str, int]:
    CATALOG_DIR.mkdir(exist_ok=True)
    missing: dict[str, int] = {}
    for prefix, lang in LOCALES.items():
        path = CATALOG_DIR / f"{lang}.po"
        catalog, n = merge_catalog(path, lang, seen)
        po.save(path, catalog)
        missing[lang] = n
    return missing


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_all(check: bool) -> tuple[list[str], dict[str, int]]:
    pages = source_pages()
    paths = localized_paths(pages)
    stale: list[str] = []
    missing: dict[str, int] = {}
    js = js_strings()

    # English pages: the hreflang block, between markers.
    for rel in pages:
        if rel.startswith("partials/"):
            continue
        src = SITE / rel
        text = src.read_text(encoding="utf-8")
        new = with_hreflang(text, PageContext(rel).url_path)
        if new != text:
            if check:
                stale.append(rel)
            else:
                src.write_text(new, encoding="utf-8")

    for prefix, lang in LOCALES.items():
        cat_path = CATALOG_DIR / f"{lang}.po"
        catalog = po.load(cat_path) if cat_path.exists() else po.Catalog()
        js_dict = {}
        for s in js:
            e = catalog.find(s, "js")
            if e and e.msgstr and not e.obsolete:
                js_dict[s] = e.msgstr
        lang_missing = 0
        for rel in pages:
            ctx = PageContext(rel, prefix=prefix, lang=lang, localized_paths=paths)
            tr = Translator(catalog, rel)
            text = (SITE / rel).read_text(encoding="utf-8")
            text = _HREFLANG_OLD.sub("", text)
            out = transform(text, tr, ctx)
            if not rel.startswith("partials/"):
                out = with_hreflang(out, ctx.url_path, lang)
                out = with_js_dictionary(out, js_dict)
            out = select_current(out, prefix)
            lang_missing += len(tr.missing)
            dest = SITE / prefix / rel
            if check:
                if not dest.exists() or dest.read_text(encoding="utf-8") != out:
                    stale.append(f"{prefix}/{rel}")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(out, encoding="utf-8")
        lang_missing += len(js) - len(js_dict)
        missing[lang] = lang_missing
    return stale, missing


# ---------------------------------------------------------------------------
# Sitemap: a <url> per localised page, beside its English entry
# ---------------------------------------------------------------------------

_URL_BLOCK = re.compile(r"  <url>\n(.*?)  </url>\n", re.S)


def update_sitemap(check: bool) -> bool:
    path = SITE / "sitemap.xml"
    text = path.read_text(encoding="utf-8")
    paths = localized_paths(source_pages())
    prefixes = tuple(f"{BASE_URL}/{p}/" for p in LOCALES)
    blocks = _URL_BLOCK.findall(text)
    kept = [b for b in blocks if not any(f"<loc>{p}" in b for p in prefixes)]
    out_blocks: list[str] = []
    for b in kept:
        out_blocks.append(b)
        m = re.search(r"<loc>([^<]*)</loc>", b)
        loc = m.group(1) if m else ""
        url_path = loc[len(BASE_URL):] or "/"
        if url_path in paths:
            for prefix in LOCALES:
                out_blocks.append(b.replace(f"<loc>{loc}</loc>", f"<loc>{BASE_URL}/{prefix}{url_path}</loc>"))
    head = text[: text.index("  <url>")]
    tail = text[text.rindex("  </url>\n") + len("  </url>\n"):]
    new = head + "".join(f"  <url>\n{b}  </url>\n" for b in out_blocks) + tail
    if new == text:
        return False
    if not check:
        path.write_text(new, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if generated output or catalogues are stale, or translations are missing")
    ap.add_argument("--extract", action="store_true", help="update the catalogues only")
    args = ap.parse_args()

    seen = extract()
    if args.check:
        # Catalogues must be current: rebuild in memory and compare.
        stale_cat = []
        for prefix, lang in LOCALES.items():
            path = CATALOG_DIR / f"{lang}.po"
            catalog, _ = merge_catalog(path, lang, seen)
            if not path.exists() or po.dump(catalog) != path.read_text(encoding="utf-8"):
                stale_cat.append(path.relative_to(ROOT).as_posix())
        stale, missing = render_all(check=True)
        sitemap_stale = update_sitemap(check=True)
        problems = 0
        if stale_cat:
            problems += 1
            print("stale catalogues (run scripts/build_site_i18n.py):", *stale_cat, sep="\n  ")
        if stale:
            problems += 1
            print("stale generated pages (run scripts/build_site_i18n.py):", *stale[:20], sep="\n  ")
            if len(stale) > 20:
                print(f"  … and {len(stale) - 20} more")
        if sitemap_stale:
            problems += 1
            print("site/sitemap.xml is missing localised entries (run scripts/build_site_i18n.py)")
        for lang, n in missing.items():
            if n:
                problems += 1
                print(f"{n} untranslated strings for {lang} (run scripts/i18n/fill.py)")
        if problems:
            return 1
        print(f"site i18n: {len(seen)} messages, {len(LOCALES)} languages, everything current")
        return 0

    missing = write_catalogs(seen)
    print(f"catalogues: {len(seen)} messages; missing " + ", ".join(f"{k}={v}" for k, v in missing.items()))
    if args.extract:
        return 0
    _, missing = render_all(check=False)
    update_sitemap(check=False)
    for lang, n in missing.items():
        if n:
            print(f"  {lang}: {n} strings rendered in English until scripts/i18n/fill.py runs", file=sys.stderr)
    print(f"rendered {len(source_pages())} pages × {len(LOCALES)} languages under site/<lang>/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
