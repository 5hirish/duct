#!/usr/bin/env python3
"""Publish the docs/ fact sheets on the site, from the files in the repository.

Why this exists
---------------
The references in `docs/` (the data model, the agent ports and events, where
every credential lives, the architecture map) are the fact sheets someone
reads before installing anything. They are maintained on GitHub and will stay
there; the site must not become a second copy that drifts. So this script
does what `build_blog.py` does for posts: `docs/factsheets.json` names the
sources to publish, each is rendered here into `site/docs/<slug>.html`, the
output is committed, and CI re-runs the script with `--check` so the site can
never lag the repository. Nothing is fetched at read time, because a crawler
without JavaScript would then see an empty page, which is the failure the
blog moved away from.

Two kinds of source
-------------------
- A markdown reference is rendered into the site's chrome: nav, title, byline
  from its `**Author:** … · **Updated:** …` line, a table of contents, the
  body, and a link to the file on GitHub.
- A self-contained HTML document (the architecture map: its own styles and
  script, a figure) is copied as-is to `site/docs/embed/<slug>.html`, with a
  `noindex` meta added so the framing page owns the URL, and shown inside a
  framing page that carries the site's chrome and `<head>` requirements.
  Restyling it into the site would mean maintaining it twice.

Links
-----
A relative link in a doc names a repository path. It is rewritten to the
published page when the target is itself a fact sheet, and to the file on
GitHub otherwise; `#L123` and heading fragments survive. A link whose target
does not exist in the tree fails the build rather than shipping a 404.

The Markdown subset
-------------------
What the references use, refused beyond that. Inline: bold, italics, `code`
and links. Blocks, each starting at the beginning of a line:

    # Title                           once, first; becomes the page title
    ## Heading / ### Heading          h2 and h3, each with an anchor id
    - item / 1. item                  lists; a wrapped item continues on
                                      indented lines (nested lists are not)
    | a | b |  then  |---|---|        a table (header row, then rows)
    > Quoted words                    a quotation
    ```lang … ```                     a code block
    ---                               a rule
    **Author:** … · **Updated:** …    the byline; read, not rendered

Anything else (h4+, images, raw HTML, nested lists) raises rather than
rendering wrong. A generator that silently mangles a construct is worse than
one that refuses, because nobody reads generated output.

Listings
--------
A page is reachable only if it is also in `site/sitemap.xml` and
`site/llms.txt`, both written by hand. Both modes fail when one is missing.

Usage
-----
    python3 scripts/build_docs.py            # write site/docs/
    python3 scripts/build_docs.py --check    # exit 1 if any output is stale
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import posixpath
import re
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
OUT_DIR = SITE / "docs"
# Embeds live in their own folder, never beside a page of the same name: with
# docs/architecture.html and docs/architecture/embed.html both present, the
# extensionless /docs/architecture resolved to the directory on the dev server.
EMBED_DIR = "embed"
PARTIALS = SITE / "partials"
MANIFEST = ROOT / "docs" / "factsheets.json"

BASE = "https://getduct.ai"
REPO_URL = "https://github.com/5hirish/duct"
DEFAULT_BRANCH = "main"
OG_DIR = SITE / "assets" / "og"
GTM_ID = "GTM-PKL589SW"
AUTHOR = {"name": "Shirish Kadam", "url": "https://shirishkadam.com"}

INDEX_TITLE = "Duct docs: data model, agent contract, architecture"
INDEX_HEADLINE = "Documentation"
INDEX_LEDE = ("The fact sheets behind Duct: what it stores, how its agents are wired, "
              "where credentials live, and a map of the code. Generated from the "
              "repository, so they cannot drift from it.")
INDEX_DESCRIPTION = ("Duct's engineering fact sheets: the data model, the agent ports and event "
                     "contract, credential storage, agent evaluation and an interactive map of the "
                     "code, all generated from the repository.")

# The byline every doc carries (docs/README.md, "Naming"). The date is what the
# page shows and what the sitemap should say.
_BYLINE = re.compile(r"^\*\*Author:\*\*\s*(?P<author>.+?)\s*·\s*\*\*(?:Updated|Date):\*\*\s*(?P<date>\d{4}-\d{2}-\d{2})\s*$")
_HTML_TITLE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)
_HTML_UPDATED = re.compile(r"<b>(?:Updated|Date)</b>\s*(\d{4}-\d{2}-\d{2})")
_HTML_CHARSET = '<meta charset="utf-8">'

_ORDERED = re.compile(r"^\d+\.\s+")
_BULLET = re.compile(r"^[-*]\s+")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")

_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_PLACEHOLDER = "\x00{}\x00"


class DocError(Exception):
    pass


# ── Manifest ────────────────────────────────────────────────────────────────


def load_manifest() -> list[dict]:
    pages = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(pages, list) or not pages:
        raise DocError(f"{MANIFEST.relative_to(ROOT)}: expected a non-empty list of pages")
    seen: set[str] = set()
    for page in pages:
        for key in ("slug", "source", "kicker", "description"):
            if not page.get(key):
                raise DocError(f"{MANIFEST.relative_to(ROOT)}: a page is missing {key!r}: {page}")
        if not re.fullmatch(r"[a-z0-9-]+", page["slug"]):
            raise DocError(f"{page['slug']}: slugs are lowercase letters, digits and dashes")
        if page["slug"] in seen:
            raise DocError(f"{page['slug']}: listed twice")
        seen.add(page["slug"])
        if not (ROOT / page["source"]).is_file():
            raise DocError(f"{page['slug']}: source {page['source']} does not exist")
        # The limits Google renders in full; STYLE.md keeps them for every page.
        if not 140 <= len(page["description"]) <= 160:
            raise DocError(f"{page['slug']}: description is {len(page['description'])} characters, needs 140-160")
    return pages


# ── Inline markdown ─────────────────────────────────────────────────────────


class LinkResolver:
    """Turn a doc's relative links into site or GitHub URLs."""

    def __init__(self, source: str, slug: str, by_source: dict[str, str]):
        self.dir = posixpath.dirname(source)
        self.slug = slug
        self.by_source = by_source

    def __call__(self, url: str) -> str:
        if url.startswith(("http://", "https://", "mailto:", "#")):
            return url
        path, _, fragment = url.partition("#")
        target = posixpath.normpath(posixpath.join(self.dir, path))
        suffix = f"#{fragment}" if fragment else ""
        if target in self.by_source:
            return f"/docs/{self.by_source[target]}{suffix}"
        absolute = ROOT / target
        if absolute.is_dir():
            return f"{REPO_URL}/tree/{DEFAULT_BRANCH}/{target}/"
        if absolute.is_file():
            return f"{REPO_URL}/blob/{DEFAULT_BRANCH}/{target}{suffix}"
        raise DocError(f"{self.slug}: link {url!r} points at {target}, which does not exist")


def inline(text: str, resolve: LinkResolver) -> str:
    """Escape, then mark up. Code spans are lifted out first so nothing inside
    them is treated as markup, which is where every `**` and `_` in a code
    sample would otherwise go wrong."""
    text = html.escape(text, quote=False)
    spans: list[str] = []

    def lift(m: re.Match) -> str:
        spans.append(f"<code>{m.group(1)}</code>")
        return _PLACEHOLDER.format(len(spans) - 1)

    text = _CODE.sub(lift, text)
    text = _LINK.sub(lambda m: f'<a href="{html.escape(resolve(html.unescape(m.group(2))), quote=True)}">{m.group(1)}</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub("\x00(\\d+)\x00", lambda m: spans[int(m.group(1))], text)


def plain(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ── Block markdown ──────────────────────────────────────────────────────────


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def render_table(rows: list[str], resolve: LinkResolver, slug: str, where: int) -> str:
    if len(rows) < 2 or not _TABLE_SEP.match(rows[1].strip()):
        raise DocError(f"{slug}: table at line {where} has no |---| separator row")
    header = split_row(rows[0])
    body = [split_row(r) for r in rows[2:]]
    for r in body:
        if len(r) != len(header):
            raise DocError(f"{slug}: table at line {where} has a row with {len(r)} cells, header has {len(header)}")
    head = "".join(f"<th>{inline(c, resolve)}</th>" for c in header)
    rows_html = "\n".join("<tr>" + "".join(f"<td>{inline(c, resolve)}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="table-wrap"><table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n{rows_html}\n</tbody>\n</table></div>'


def render_markdown(body: str, slug: str, resolve: LinkResolver) -> tuple[dict, list[dict]]:
    """Return (meta, blocks). meta has title, author and updated; each block
    is {"tag", "html"} plus "id"/"text" on a heading."""
    meta: dict[str, str] = {}
    blocks: list[dict] = []
    ids: set[str] = set()
    lines = body.split("\n")
    i = 0

    def heading_id(text: str) -> str:
        base = slugify(text) or "section"
        candidate, n = base, 2
        while candidate in ids:
            candidate, n = f"{base}-{n}", n + 1
        ids.add(candidate)
        return candidate

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        n = i + 1

        if not line:
            i += 1
            continue

        if line.startswith("```"):
            lang = line[3:].strip()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            if i >= len(lines):
                raise DocError(f"{slug}: code fence opened at line {n} never closes")
            i += 1
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            blocks.append({"tag": "pre", "html": f"<pre><code{cls}>{html.escape(chr(10).join(code))}</code></pre>"})
            continue

        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            blocks.append({"tag": "table", "html": render_table(rows, resolve, slug, n)})
            continue

        if line.startswith(">"):
            quoted = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quoted.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append({"tag": "blockquote", "html": f"<blockquote><p>{inline(' '.join(quoted), resolve)}</p></blockquote>"})
            continue

        if line == "---":
            blocks.append({"tag": "hr", "html": "<hr/>"})
            i += 1
            continue

        m = _HEADING.match(line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                if blocks or "title" in meta:
                    raise DocError(f"{slug}: a second h1 at line {n}; the title is the only h1")
                meta["title"] = plain(inline(text, resolve))
            elif level in (2, 3):
                hid = heading_id(text)
                rendered = inline(text, resolve)
                blocks.append({"tag": f"h{level}", "id": hid, "text": plain(rendered),
                               "html": f'<h{level} id="{hid}">{rendered}</h{level}>'})
            else:
                raise DocError(f"{slug}: h{level} at line {n}; references use h2 and h3 under the title")
            i += 1
            continue

        if raw.startswith((" ", "\t")):
            raise DocError(f"{slug}: indented line {n} outside a list item (a nested list?): {line[:60]!r}")

        if line.startswith(("![", "<")):
            raise DocError(f"{slug}: unsupported construct at line {n} (image or raw HTML): {line[:60]!r}")

        marker = _ORDERED if _ORDERED.match(line) else _BULLET if _BULLET.match(line) else None
        if marker:
            items: list[str] = []
            while i < len(lines):
                current = lines[i]
                if marker.match(current.strip()) and not current.startswith((" ", "\t")):
                    items.append(marker.sub("", current.strip()))
                    i += 1
                elif current.startswith((" ", "\t")) and current.strip():
                    if _BULLET.match(current.strip()) or _ORDERED.match(current.strip()):
                        raise DocError(f"{slug}: nested list at line {i + 1}; flatten it")
                    items[-1] += " " + current.strip()
                    i += 1
                elif not current.strip():
                    # A blank line inside a list only if the list carries on after it.
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and marker.match(lines[j].strip()) and not lines[j].startswith((" ", "\t")):
                        i = j
                        continue
                    break
                else:
                    break
            tag = "ol" if marker is _ORDERED else "ul"
            blocks.append({"tag": tag, "html": f"<{tag}>\n" + "\n".join(f"<li>{inline(t, resolve)}</li>" for t in items) + f"\n</{tag}>"})
            continue

        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith((" ", "\t")) \
                and not _HEADING.match(lines[i].strip()) \
                and not lines[i].strip().startswith(("|", ">", "```", "- ", "* ")) \
                and not _ORDERED.match(lines[i].strip()) and lines[i].strip() != "---":
            para.append(lines[i].strip())
            i += 1
        text = " ".join(para)
        byline = _BYLINE.match(text)
        if byline:
            meta["author"], meta["updated"] = byline.group("author"), byline.group("date")
            continue
        blocks.append({"tag": "p", "html": f"<p>{inline(text, resolve)}</p>"})

    for key in ("title", "author", "updated"):
        if key not in meta:
            raise DocError(f"{slug}: no {key} found (a title h1 and an **Author:** … · **Updated:** … line are required)")
    return meta, blocks


# ── Page ────────────────────────────────────────────────────────────────────


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def load_partial(name: str) -> str:
    """Inline a shared partial. A runtime fetch is not a crawlable link."""
    return (PARTIALS / name).read_text(encoding="utf-8").strip()


def ld_script(data: dict) -> str:
    return '<script type="application/ld+json">\n' + json.dumps(data, ensure_ascii=False, indent=2) + "\n</script>"


def iso(date_text: str) -> str:
    return datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()


def og_image_for(slug: str) -> str:
    name = "docs.jpg" if slug == "index" else f"docs-{slug}.jpg"
    if not (OG_DIR / name).exists():
        raise DocError(f"{slug}: no card at site/assets/og/{name}. Run: node scripts/build_og_images.mjs")
    return f"{BASE}/assets/og/{name}"


PAGE_STYLE = """<style>
.doc-header { max-width: 760px; margin: 0 auto; padding: 72px 24px 0; }
.doc-header .tag { margin-bottom: 18px; }
.doc-header h1 { font-family: var(--serif); font-size: clamp(28px, 4vw, 42px); line-height: 1.15; color: var(--navy); margin-bottom: 16px; letter-spacing: -.5px; }
.doc-meta { font-size: 13px; color: var(--navy-3); display: flex; flex-wrap: wrap; gap: 8px 18px; margin-bottom: 8px; }
.doc-meta a { color: var(--navy-2); text-decoration: none; border-bottom: 1px solid var(--border); }
.doc-meta a:hover { border-color: var(--navy); }
.doc-lede { max-width: 760px; margin: 0 auto; padding: 0 24px; font-size: 16px; font-weight: 300; line-height: 1.7; color: var(--navy-3); }
.doc-toc { max-width: 760px; margin: 28px auto 0; padding: 20px 24px; }
.doc-toc-inner { border: 1px solid var(--border); border-radius: var(--r-lg); padding: 18px 22px; background: var(--off); }
.doc-toc-title { font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--navy-3); margin-bottom: 10px; }
.doc-toc ol { margin: 0; padding-left: 20px; columns: 2; column-gap: 32px; }
.doc-toc li { font-size: 14px; line-height: 1.6; margin: 0 0 4px; break-inside: avoid; }
.doc-toc a { color: var(--navy-2); text-decoration: none; }
.doc-toc a:hover { color: var(--orange); }
.prose { max-width: 760px; padding-top: 24px; }
.prose h2 { scroll-margin-top: 88px; }
.prose h3 { scroll-margin-top: 88px; }
.prose h2 code, .prose h3 code { font-size: .8em; }
.prose li p { margin: 0; }
.table-wrap { overflow-x: auto; margin: 0 0 28px; -webkit-overflow-scrolling: touch; width: min(1040px, 100vw - 48px); position: relative; left: 50%; transform: translateX(-50%); }
.prose table { border-collapse: collapse; width: 100%; font-size: 14px; line-height: 1.55; }
.prose th, .prose td { text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--navy-3); font-weight: 300; }
.prose th { font-weight: 600; color: var(--navy); border-bottom: 2px solid var(--border); white-space: nowrap; }
.prose th code { white-space: nowrap; }
.prose tbody tr:hover td { background: var(--off); }
.doc-nav { display: flex; justify-content: space-between; gap: 24px; max-width: 760px; margin: 0 auto; padding: 8px 24px 72px; }
.doc-nav a { font-size: 14px; font-weight: 500; color: var(--navy-3); text-decoration: none; max-width: 46%; }
.doc-nav a:hover { color: var(--navy); }
.doc-nav-next { margin-left: auto; text-align: right; }
.doc-frame-wrap { max-width: 1240px; margin: 28px auto 0; padding: 0 24px 24px; }
.doc-frame { display: block; width: 100%; height: max(640px, min(1400px, calc(100vh - 96px))); border: 1px solid var(--border); border-radius: var(--r-lg); background: var(--off); }
.doc-frame-actions { display: flex; gap: 18px; margin-top: 12px; font-size: 13px; }
.doc-frame-actions a { color: var(--navy-2); text-decoration: none; border-bottom: 1px solid var(--border); }
.doc-frame-actions a:hover { border-color: var(--navy); }
.doc-list { max-width: 760px; margin: 0 auto; padding: 40px 24px 96px; }
.doc-item { display: block; text-decoration: none; color: inherit; padding: 26px 0; border-bottom: 1px solid var(--border); }
.doc-item:first-child { border-top: 1px solid var(--border); }
.doc-item .tag { font-size: 11px; margin-bottom: 8px; }
.doc-item h2 { font-family: var(--serif); font-size: 22px; line-height: 1.25; color: var(--navy); margin: 0 0 8px; transition: color .15s; }
.doc-item:hover h2 { color: var(--orange); }
.doc-item p { font-size: 15px; font-weight: 300; line-height: 1.65; color: var(--navy-3); margin: 0 0 10px; }
.doc-item-meta { font-size: 12px; color: var(--navy-3); display: flex; gap: 16px; }
@media (max-width: 640px) {
  .doc-toc ol { columns: 1; }
  .doc-nav { flex-direction: column; gap: 12px; }
  .doc-nav a { max-width: 100%; }
  .doc-nav-next { margin-left: 0; text-align: left; }
  .doc-frame { height: max(560px, calc(100vh - 120px)); }
}
</style>"""


def head(*, title: str, canonical: str, description: str, og_image: str, og_type: str,
         ld: list[dict], modified: str | None = None) -> str:
    modified_meta = f'\n<meta property="article:modified_time" content="{modified}"/>' if modified else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link rel="icon" href="../assets/icon.svg" type="image/svg+xml"/>
<link rel="apple-touch-icon" href="../assets/apple-icon.svg"/>
<title>{esc(title)}</title>
<link rel="canonical" href="{canonical}"/>
<meta name="description" content="{esc(description)}"/>
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1"/>
<meta property="og:type" content="{og_type}"/>
<meta property="og:locale" content="en_US"/>
<meta property="og:url" content="{canonical}"/>
<meta property="og:title" content="{esc(title)}"/>
<meta property="og:description" content="{esc(description)}"/>
<meta property="og:image" content="{og_image}"/>
<meta property="og:image:width" content="1200"/>
<meta property="og:image:height" content="630"/>
<meta property="og:site_name" content="Duct"/>{modified_meta}
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{esc(title)}"/>
<meta name="twitter:description" content="{esc(description)}"/>
<meta name="twitter:image" content="{og_image}"/>
<link rel="stylesheet" href="../assets/duct.css"/>
<script src="../assets/config.js" defer></script>
{chr(10).join(ld_script(d) for d in ld)}
{PAGE_STYLE}
</head>
<body>

<a href="#main-content" class="skip-link">Skip to content</a>

<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM_ID}" height="0" width="0" style="display:none;visibility:hidden" title="Google Tag Manager"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
"""


def tail() -> str:
    return f"""
{load_partial('footer-expanded.html')}

<script src="../assets/duct.js" defer></script>
<script src="../assets/duct-download.js" defer></script>

</body>
</html>
"""


def breadcrumbs(*trail: tuple[str, str]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "inLanguage": "en",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate((("Home", f"{BASE}/"), ("Docs", f"{BASE}/docs/")) + trail)
        ],
    }


def tech_article(page: dict, title: str, updated: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "inLanguage": "en",
        "headline": title,
        "description": page["description"],
        "url": f"{BASE}/docs/{page['slug']}",
        "dateModified": iso(updated),
        "author": {"@type": "Person", "name": AUTHOR["name"], "url": AUTHOR["url"]},
        "publisher": {"@type": "Organization", "name": "Duct", "url": BASE},
        "isPartOf": {"@type": "CollectionPage", "name": INDEX_HEADLINE, "url": f"{BASE}/docs/"},
        "license": f"{REPO_URL}/blob/{DEFAULT_BRANCH}/LICENSE",
    }


def doc_header(page: dict, title: str, author: str, updated: str) -> str:
    source = page["source"]
    return f"""<header class="doc-header">
<p class="tag">Docs · {esc(page['kicker'])}</p>
<h1>{esc(title)}</h1>
<div class="doc-meta">
<span>Updated {esc(updated)}</span>
<span>{esc(author)}</span>
<a href="{REPO_URL}/blob/{DEFAULT_BRANCH}/{source}" rel="noopener">Source: {esc(source)}</a>
<a href="{REPO_URL}/edit/{DEFAULT_BRANCH}/{source}" rel="noopener">Edit on GitHub</a>
</div>
</header>"""


def doc_nav(pages: list[dict], idx: int) -> str:
    links = []
    if idx > 0:
        prev_page = pages[idx - 1]
        links.append(f'<a class="doc-nav-prev" href="/docs/{prev_page["slug"]}">← {esc(prev_page["title"])}</a>')
    links.append('<a class="doc-nav-all" href="/docs/">All docs</a>')
    if idx + 1 < len(pages):
        next_page = pages[idx + 1]
        links.append(f'<a class="doc-nav-next" href="/docs/{next_page["slug"]}">{esc(next_page["title"])} →</a>')
    return '<nav class="doc-nav" aria-label="More documentation">\n' + "\n".join(links) + "\n</nav>"


def contents(blocks: list[dict]) -> str:
    sections = [b for b in blocks if b["tag"] == "h2"]
    if len(sections) < 2:
        return ""
    items = "\n".join(f'<li><a href="#{b["id"]}">{esc(b["text"])}</a></li>' for b in sections)
    return (f'<nav class="doc-toc" aria-label="On this page">\n<div class="doc-toc-inner">\n'
            f'<p class="doc-toc-title">On this page</p>\n<ol>\n{items}\n</ol>\n</div>\n</nav>\n')


def render_markdown_page(page: dict, pages: list[dict], idx: int) -> str:
    slug, title, updated = page["slug"], page["title"], page["updated"]
    blocks = page["blocks"]
    canonical = f"{BASE}/docs/{slug}"
    generated_note = f"<!-- GENERATED FILE — edit {page['source']} and run scripts/build_docs.py -->"
    body_html = "\n".join(b["html"] for b in blocks)
    return (head(title=f"{title} — Duct docs", canonical=canonical, description=page["description"],
                 og_image=og_image_for(slug), og_type="article", modified=iso(updated),
                 ld=[tech_article(page, title, updated), breadcrumbs((title, canonical))])
            + f"""
{generated_note}
{load_partial('nav-docs.html')}

<main id="main-content">
{doc_header(page, title, page['author'], updated)}
{contents(blocks)}
<article class="prose">
{body_html}
</article>
{doc_nav(pages, idx)}
</main>
""" + tail())


def render_frame_page(page: dict, pages: list[dict], idx: int) -> str:
    slug, title, updated = page["slug"], page["title"], page["updated"]
    canonical = f"{BASE}/docs/{slug}"
    embed = f"/docs/{EMBED_DIR}/{slug}"
    return (head(title=f"{title} — Duct docs", canonical=canonical, description=page["description"],
                 og_image=og_image_for(slug), og_type="article", modified=iso(updated),
                 ld=[tech_article(page, title, updated), breadcrumbs((title, canonical))])
            + f"""
<!-- GENERATED FILE — edit {page['source']} and run scripts/build_docs.py -->
{load_partial('nav-docs.html')}

<main id="main-content">
{doc_header(page, title, page['author'], updated)}
<p class="doc-lede">{esc(page['description'])}</p>
<div class="doc-frame-wrap">
<iframe class="doc-frame" src="{embed}" title="{esc(title)}" loading="lazy"></iframe>
<p class="doc-frame-actions"><a href="{embed}">Open full screen ↗</a></p>
</div>
{doc_nav(pages, idx)}
</main>
""" + tail())


def render_embed(page: dict) -> str:
    text = (ROOT / page["source"]).read_text(encoding="utf-8")
    if _HTML_CHARSET not in text:
        raise DocError(f"{page['slug']}: {page['source']} has no {_HTML_CHARSET}; the noindex tag goes after it")
    # The framing page is the canonical address. The copy must not compete
    # with it in search, and it must stay byte-for-byte the source otherwise.
    return text.replace(_HTML_CHARSET, f'{_HTML_CHARSET}\n<meta name="robots" content="noindex">', 1)



def render_index(pages: list[dict]) -> str:
    canonical = f"{BASE}/docs/"
    items = "\n".join(
        f"""<a class="doc-item" href="/docs/{p['slug']}">
<span class="tag">{esc(p['kicker'])}</span>
<h2>{esc(p['title'])}</h2>
<p>{esc(p['description'])}</p>
<div class="doc-item-meta"><span>Updated {esc(p['updated'])}</span><span>{esc(p['source'])}</span></div>
</a>""" for p in pages)
    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "inLanguage": "en",
        "name": f"Duct {INDEX_HEADLINE.lower()}",
        "url": canonical,
        "description": INDEX_DESCRIPTION,
        "isPartOf": {"@type": "WebSite", "name": "Duct", "url": BASE},
        "hasPart": [{"@type": "TechArticle", "name": p["title"], "url": f"{BASE}/docs/{p['slug']}"} for p in pages],
    }
    return (head(title=INDEX_TITLE, canonical=canonical, description=INDEX_DESCRIPTION,
                 og_image=og_image_for("index"), og_type="website", ld=[collection, breadcrumbs()])
            + f"""
<!-- GENERATED FILE — edit docs/factsheets.json and run scripts/build_docs.py -->
{load_partial('nav-docs.html')}

<main id="main-content">
<section class="blog-hero">
<h1>{INDEX_HEADLINE}</h1>
<p>{esc(INDEX_LEDE)}</p>
</section>
<div class="doc-list">
{items}
</div>
</main>
""" + tail())


# ── Driver ──────────────────────────────────────────────────────────────────


def build() -> dict[str, str]:
    pages = load_manifest()
    by_source = {p["source"]: p["slug"] for p in pages}
    for page in pages:
        source = ROOT / page["source"]
        if source.suffix == ".md":
            resolve = LinkResolver(page["source"], page["slug"], by_source)
            meta, blocks = render_markdown(source.read_text(encoding="utf-8"), page["slug"], resolve)
            page.update(meta, blocks=blocks, kind="markdown")
        elif source.suffix == ".html":
            text = source.read_text(encoding="utf-8")
            title, updated = _HTML_TITLE.search(text), _HTML_UPDATED.search(text)
            if not title or not updated:
                raise DocError(f"{page['slug']}: {page['source']} needs an <h1> and a <b>Updated</b> date in its masthead")
            page.update(title=plain(title.group(1)).strip(), updated=updated.group(1), author=AUTHOR["name"], kind="html")
        else:
            raise DocError(f"{page['slug']}: {page['source']} is neither .md nor .html")

    out = {"index.html": render_index(pages)}
    for idx, page in enumerate(pages):
        if page["kind"] == "markdown":
            out[f"{page['slug']}.html"] = render_markdown_page(page, pages, idx)
        else:
            out[f"{page['slug']}.html"] = render_frame_page(page, pages, idx)
            out[f"{EMBED_DIR}/{page['slug']}.html"] = render_embed(page)
    return out


def listing_errors(pages_urls: list[str]) -> list[str]:
    """A page nobody can find is not published. Both files are hand-written."""
    errors = []
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    llms = (SITE / "llms.txt").read_text(encoding="utf-8")
    for url in pages_urls:
        if f"<loc>{url}</loc>" not in sitemap:
            errors.append(f"site/sitemap.xml has no entry for {url}")
        if url not in llms:
            errors.append(f"site/llms.txt does not mention {url}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Render docs/ fact sheets into site/docs/")
    parser.add_argument("--check", action="store_true", help="fail if any generated page is stale")
    args = parser.parse_args()

    try:
        pages = build()
    except DocError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    urls = [f"{BASE}/docs/"] + [f"{BASE}/docs/{name[:-5]}" for name in pages if name != "index.html" and "/" not in name]
    errors = listing_errors(urls)

    stale = []
    for name, content in pages.items():
        target = OUT_DIR / name
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                stale.append(name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    # Output nobody asked for is a page nobody maintains.
    expected = set(pages)
    for path in OUT_DIR.rglob("*.html") if OUT_DIR.exists() else []:
        rel = path.relative_to(OUT_DIR).as_posix()
        if rel not in expected:
            if args.check:
                stale.append(f"{rel} (not in docs/factsheets.json)")
            else:
                path.unlink()
                print(f"removed site/docs/{rel}: not in docs/factsheets.json")
                if path.parent != OUT_DIR and not any(path.parent.iterdir()):
                    path.parent.rmdir()

    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    if args.check:
        for name in stale:
            print(f"STALE: site/docs/{name} — run python3 scripts/build_docs.py", file=sys.stderr)
        if not stale and not errors:
            print(f"site/docs: {len(pages)} files current")
        return 1 if (stale or errors) else 0

    print(f"wrote {len(pages)} files to site/docs/")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
