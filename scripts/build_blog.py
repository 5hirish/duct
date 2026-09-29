#!/usr/bin/env python3
"""Pre-render blog posts to static HTML.

Why this exists
---------------
`site/blog/post.html` renders a post in the browser: it fetches the Markdown and
parses it with marked.js. That is invisible to any crawler that does not execute
JavaScript, which is most AI crawlers. Measured against production, GPTBot
received 49 characters of body text for a 6,000-word article, the title
"Duct Insights", an empty description, and the canonical `/blog/post` shared by
every post.

So the Markdown is rendered here instead, at authoring time, into a real HTML
file per post. Output is committed and CI re-runs this script to verify the
tree matches (`--check`), which is what keeps generated and source in sync
without adding a build step to the deploy.

Shared nav and footer are inlined rather than left as `data-duct-partial`
placeholders, for the same reason: a runtime fetch is not a crawlable link.
Regeneration is the only way these copies change, so they cannot drift.

The Markdown subset
-------------------
Small, and extended only when a post needs a construct. Inline: bold, italics,
`code` and links. Blocks, each starting at the beginning of a line:

    ## Heading / ### Heading          h2 and h3, each with an anchor id
    - item / 1. item                  bullet and ordered lists (not nested)
    ---                               a rule
    ![Alt](assets/<slug>/x.svg "Caption")
                                      a figure; its size is read from the file,
                                      and `x-768.webp` beside it joins the srcset
    | a | b |  then  |---|---|        a table (header row, then rows)
    > Quoted words                    a quotation; a final `> -- [Who, Title](url)`
                                      line attributes it and sets `cite`
    ```lang … ```                     a code block
    [!github](https://github.com/o/r "What it is")
                                      a repository card, drawn here: no widget,
                                      no request to GitHub from the reader
    [!youtube](https://www.youtube.com/watch?v=ID "Talk title, speaker")
                                      a click-to-play video under its own
                                      thumbnail, served from this site: nothing
                                      is fetched from YouTube until play

Anything else (h1, h4+, raw HTML, nested lists) raises rather than rendering
wrong. A generator that silently mangles a construct is worse than one that
refuses, because nobody reads generated output.

Structured data
---------------
A post carries a `BlogPosting` whose `citation` lists every outside source it
links, a `BreadcrumbList`, and, when it has a `## FAQ` section of `###`
questions, a `FAQPage` built from the same rendered text the reader sees, so
the two cannot say different things.

Front matter
------------
Required: title, date, author, category, tags, excerpt, readTime.

    category     one of CATEGORIES below: the post's single primary shelf
    tags         comma-separated, 1-6, lowercase topics ("agent memory, evals");
                 shown under the post, and the BlogPosting's keywords
    description  the meta description, 140-160 characters (default: excerpt)
    seoTitle     the <title>, at most 60 characters (default: "<title> — Duct blog")
    updated      the last substantive revision: dateModified, and the byline
    hero         an image under the title, relative to site/blog/; needs heroAlt
    audience     which closer ends the post, growth or builders (default: the
                 category's)
    link         makes this a link post (below): the https address of the post
                 where it was published

Link posts
----------
A post written somewhere else, shared the way a retweet shares a tweet: a card
on the blog index that goes to the original, and nothing else. No page is made
here, so there is no second copy for a search engine to weigh against the
first, and the post is left out of the sitemap, the feed, llms.txt and the
previous/next links, which all name pages on this site. The file is front
matter only; a body is an error, because it would never be shown. The card is
its OG card, drawn from the same front matter like any other post's.

The blog index
--------------
The card grid on site/blog/index.html, and the category filter above it, sit
between `blog-index:start` / `blog-index:end` markers and are written here from
the front matter, newest first. The page around them is hand-written. A card
typed by hand drifted from its post once; a generated one cannot.

Listings
--------
A post is reachable only if it is also in the sitemap, the RSS feed and
llms.txt, all three written by hand. Both modes fail when one is missing.

Usage
-----
    python3 scripts/build_blog.py                     # write the posts and the index grid
    python3 scripts/build_blog.py --check             # exit 1 if anything is stale
    python3 scripts/build_blog.py --fetch-thumbnails  # once per new video: save its
                                                      # thumbnail beside the post (network)
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
POSTS = SITE / "blog" / "posts"
OUT_DIR = SITE / "blog"
PARTIALS = SITE / "partials"

BASE = "https://getduct.ai"
REPO_URL = "https://github.com/5hirish/duct"
OG_DIR = SITE / "assets" / "og"
GTM_ID = "GTM-PKL589SW"
AUTHOR = {
    "name": "Shirish Kadam",
    "url": "https://shirishkadam.com",
    "sameAs": [
        "https://github.com/5hirish",
        "https://x.com/5hirish",
        "https://youtube.com/@5hirish",
    ],
}

REQUIRED_FRONT_MATTER = ("title", "date", "author", "category", "tags", "excerpt", "readTime")

# The primary category is a fixed shelf, so the index reads as five kinds of
# post rather than one label per post; the topics go in tags. Each category
# names the closer its readers get unless a post overrides `audience`.
CATEGORIES = {
    "Engineering": "builders",   # how Duct's agent and product are built, with the code
    "Design": "builders",        # interface and product design decisions, and why
    "Growth": "growth",          # practical guides for running growth without a data team
    "Announcement": "growth",    # launches and releases worth more than a changelog line
    "Story": "growth",           # why Duct exists, what building it in public taught us
}
MAX_TAGS = 6

# Links to these are Duct's own pages, not sources the post draws on, so they
# stay out of the BlogPosting's `citation` list.
OWN_URL_PREFIXES = (BASE, "https://github.com/5hirish")

# A post this long gets a contents list; the two early posts (5-6 minutes)
# read fine without one.
TOC_MIN_READ_MINUTES = 8
TOC_MIN_SECTIONS = 4

FAQ_HEADING = re.compile(r"^(faq|frequently asked questions)\b", re.I)

# Image slots, for `sizes`: the prose measure is 700px less its 24px gutters.
# The hero keeps to the same measure: at 880px it filled the first screen and
# pushed the answer-first paragraph below the fold.
FIGURE_SIZES = "(max-width: 700px) calc(100vw - 48px), 652px"
HERO_SIZES = FIGURE_SIZES
SRCSET_VARIANTS = (768, 1536)

# The closer every post ends on. A post carries no pitch of its own; which
# bridge it gets depends on who it was written for. Growth readers are sold
# by the product; builders are sold by the code, so theirs leads to the repo.
BRIDGES = {
    "growth": {
        "headline": "Reading three tools together is the whole job. Duct does it on your machine.",
        "body": "Ask why signups dropped. Duct reads Search Console, GA4 and your ads and revenue tools together, answers with the sources it read, and proposes the change. You approve it. Open source, free with your own keys.",
        "actions": '<a href="/download" class="btn btn-orange" data-duct-download>Download Duct&nbsp;↓</a><a href="/" class="duct-bridge-link">How Duct works&nbsp;→</a>',
        "shot": "insights-session",
        "alt": "An insights session: the question, the sources it read, two findings, and the brief beside it",
        "caption": "Why are signups down? Asked once, answered from four tools.",
    },
    "builders": {
        "headline": "Every rule in this post is a file you can read.",
        "body": "Duct is an open-source agent for product and growth teams. Its loop, approval policy, eval gate and memory live in one MIT-licensed repository, next to the tests that hold them. Read it, fork it, or run it with your own keys.",
        "actions": f'<a href="{REPO_URL}" class="btn btn-orange" rel="noopener">Star Duct on GitHub</a><a href="/download" class="duct-bridge-link" data-duct-download>Download Duct&nbsp;↓</a>',
        "shot": "review-card",
        "alt": "A change set waiting for approval: two changes will apply, one is held because it breaks the budget guardrail",
        "caption": "Authority lives in code: the agent proposes, a person approves.",
    },
}


class PostError(Exception):
    """A post the generator refuses to render, with the reason."""


# ── Markdown ────────────────────────────────────────────────────────────────

_INLINE_CODE = re.compile(r"`([^`]+)`")
_INLINE_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_INLINE_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_INLINE_EM = re.compile(r"(?<![*\w])\*([^*\s][^*]*?)\*(?![*\w])")
_ORDERED = re.compile(r"^\d+\.\s+")
_BULLET = re.compile(r"^[-*]\s+")
_IMAGE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)$')
_EMBED = re.compile(r'^\[!(\w+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)$')
_GITHUB_REPO = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/?$")
_YOUTUBE_ID = re.compile(r"^https://(?:www\.youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})$")
_TABLE_RULE = re.compile(r"^\|?(\s*:?-{3,}:?\s*\|)+\s*(:?-{3,}:?)?\s*\|?$")
_BLOCK_START = re.compile(r"^(#|\d+\.\s|[-*]\s|```|\||>|!\[|\[!)")
_TAG = re.compile(r"<[^>]+>")


def _inline(text: str) -> str:
    """Escape, then re-introduce only the inline markup we support.

    Escaping first is what makes this safe: a post can contain `<` or `&`
    without the generator emitting broken markup or, worse, live HTML. Code
    spans are lifted out before anything else so `**` or `[x](y)` inside one
    stays literal.
    """
    spans: list[str] = []

    def lift(m: re.Match) -> str:
        spans.append(f"<code>{html.escape(m.group(1), quote=False)}</code>")
        return f"\x00{len(spans) - 1}\x00"

    out = html.escape(_INLINE_CODE.sub(lift, text), quote=False)
    out = _INLINE_LINK.sub(
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', out
    )
    out = _INLINE_BOLD.sub(r"<strong>\1</strong>", out)
    out = _INLINE_EM.sub(r"<em>\1</em>", out)
    return re.sub("\x00(\\d+)\x00", lambda m: spans[int(m.group(1))], out)


def plain(fragment: str) -> str:
    """The text a reader sees in a rendered fragment: no tags, entities decoded."""
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub("", fragment))).strip()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", plain(text).lower()).strip("-")


def image_size(path: pathlib.Path) -> tuple[int, int]:
    """Width and height from the file header, stdlib only.

    CI runs this script on a bare Python, so there is no Pillow to ask. Every
    `<img>` needs both numbers, or the page shifts as each image loads.
    """
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8 ":
            return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                    int.from_bytes(data[28:30], "little") & 0x3FFF)
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01, 0xFF) or 0xD0 <= marker <= 0xD7:
                i += 1 if marker == 0xFF else 2
                continue
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
            i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    if path.suffix == ".svg":
        root = re.search(r"<svg\b[^>]*>", data.decode("utf-8"))
        box = root and re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)\s*"', root.group(0))
        if box:
            return round(float(box.group(1))), round(float(box.group(2)))
    raise PostError(f"cannot read the size of {path.relative_to(ROOT)}")


def img_tag(src: str, alt: str, sizes: str, *, eager: bool = False) -> str:
    """An `<img>` with its size, and a srcset when smaller variants sit beside it."""
    path = (OUT_DIR / src).resolve()
    if not path.is_file():
        raise PostError(f"image {src} not found (paths are relative to site/blog/)")
    width, height = image_size(path)
    candidates = []
    for w in SRCSET_VARIANTS:
        variant = path.with_name(f"{path.stem}-{w}{path.suffix}")
        if w < width and variant.is_file():
            candidates.append(f"{src.rsplit('.', 1)[0]}-{w}{path.suffix} {w}w")
    srcset = ""
    if candidates:
        candidates.append(f"{src} {width}w")
        srcset = f' srcset="{", ".join(candidates)}" sizes="{sizes}"'
    loading = ' fetchpriority="high"' if eager else ' loading="lazy" decoding="async"'
    return (f'<img src="{esc(src)}"{srcset} width="{width}" height="{height}"{loading} '
            f'alt="{esc(alt)}"/>')


def youtube_thumbnail(slug: str, video_id: str) -> str:
    """Where a video's thumbnail lives, relative to site/blog/."""
    return f"assets/{slug}/youtube-{video_id}.jpg"


def render_embed(kind: str, url: str, note: str | None, where: str, slug: str) -> str:
    if kind == "github":
        repo = _GITHUB_REPO.match(url)
        if not repo:
            raise PostError(f"{where}: [!github] takes a repository URL, got {url}")
        if not note:
            raise PostError(f'{where}: [!github] needs a description: [!github]({url} "What it is")')
        return (
            f'<a class="post-embed" href="{esc(url)}" rel="noopener">'
            '<svg class="ic" aria-hidden="true"><use href="/assets/icons.svg#github"/></svg>'
            f'<span class="post-embed-body"><span class="post-embed-title">{esc(repo.group(1))}/'
            f'<strong>{esc(repo.group(2))}</strong></span>'
            f'<span class="post-embed-desc">{_inline(note)}</span></span>'
            '<span class="post-embed-host">github.com</span></a>'
        )
    if kind == "youtube":
        video = _YOUTUBE_ID.match(url)
        if not video or not note:
            raise PostError(f'{where}: [!youtube] takes a watch URL and a title: [!youtube]({url} "Title, speaker")')
        # A facade, not a player: the thumbnail is a copy served from this
        # site and the privacy-enhanced player loads only on the reader's
        # click, so a page view sends YouTube nothing and nothing loads
        # outside the consent gate uninvited.
        thumb = youtube_thumbnail(slug, video.group(1))
        if not (OUT_DIR / thumb).is_file():
            raise PostError(f"{where}: no thumbnail at site/blog/{thumb}. "
                            f"Run: python3 scripts/build_blog.py --fetch-thumbnails")
        return (
            f'<figure class="post-video"><a class="post-video-facade" href="{esc(url)}" rel="noopener" '
            f'data-youtube="{video.group(1)}" data-title="{esc(note)}">'
            f'{img_tag(thumb, "", FIGURE_SIZES)}'
            '<span class="post-video-play" aria-hidden="true"><svg class="ic"><use href="/assets/icons.svg#play"/></svg></span>'
            f'<span class="post-video-caption"><span class="post-video-title">{esc(note)}</span>'
            '<span class="post-video-note">YouTube · plays here when you press play</span></span></a></figure>'
        )
    raise PostError(f"{where}: unknown embed [!{kind}]. Add it to render_embed() first.")


def render_table(rows: list[str], where: str) -> str:
    def cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split("|")]

    if len(rows) < 3 or not _TABLE_RULE.match(rows[1].strip()):
        raise PostError(f"{where}: a table needs a header row, a |---| rule, then rows")
    head = cells(rows[0])
    body = [cells(r) for r in rows[2:]]
    for n, row in enumerate(body):
        if len(row) != len(head):
            raise PostError(
                f"{where}: table row {n + 1} has {len(row)} cells, the header has {len(head)}. "
                f"A literal | inside a cell is not supported."
            )
    label = esc(", ".join(plain(_inline(h)) for h in head))
    thead = "".join(f'<th scope="col">{_inline(h)}</th>' for h in head)
    tbody = "\n".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
    # A wide table scrolls inside its own box on a phone; the region is
    # focusable so a keyboard user can scroll it too.
    return (f'<div class="post-table" role="region" aria-label="Table: {label}" tabindex="0">\n'
            f"<table>\n<thead><tr>{thead}</tr></thead>\n<tbody>\n{tbody}\n</tbody>\n</table>\n</div>")


def render_quote(lines: list[str], where: str) -> str:
    text = [ln[1:].strip() for ln in lines]
    attribution = text.pop() if text and text[-1].startswith("-- ") else None
    if any(t.startswith("-- ") for t in text):
        raise PostError(f"{where}: a quote's attribution line must be its last line")
    paras, cur = [], []
    for t in text + [""]:
        if t:
            cur.append(t)
        elif cur:
            paras.append(f"<p>{_inline(' '.join(cur))}</p>")
            cur = []
    if not paras:
        raise PostError(f"{where}: empty quote")
    cite, caption = "", ""
    if attribution:
        source = _INLINE_LINK.search(attribution)
        if source:
            cite = f' cite="{esc(source.group(2))}"'
        caption = f"\n<figcaption>{_inline(attribution[3:].strip())}</figcaption>"
    return f'<figure class="post-quote">\n<blockquote{cite}>\n' + "\n".join(paras) + f"\n</blockquote>{caption}\n</figure>"


def render_markdown(body: str, slug: str) -> list[dict]:
    """Render the supported subset into blocks, refusing anything outside it.

    Each block is `{"tag", "html", "text"}`; the page joins the html, and the
    FAQ, contents list, word count and citations are read off the same blocks,
    so structured data is always the text on the page.
    """
    blocks: list[dict] = []
    ids: set[str] = set()
    lines = body.split("\n")
    i = 0

    def block(tag: str, markup: str) -> None:
        blocks.append({"tag": tag, "html": markup, "text": plain(markup)})

    while i < len(lines):
        line = lines[i].strip()
        where = f"{slug}: line {i + 1}"

        if not line:
            i += 1
            continue

        if line.startswith("<"):
            raise PostError(f"{where}: raw HTML. Extend render_markdown() in scripts/build_blog.py instead.")

        # A rule between two parts of a post; it rendered as a literal "---"
        # paragraph before this was handled.
        if line == "---":
            block("hr", "<hr/>")
            i += 1
            continue

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level not in (2, 3):
                raise PostError(
                    f"{where}: h{level}. Posts use h2 and h3 only: the page title is "
                    f"the h1, and skipping levels breaks the outline."
                )
            inner = _inline(line[level:].strip())
            anchor = base = slugify(inner)
            n = 2
            while anchor in ids:
                anchor, n = f"{base}-{n}", n + 1
            ids.add(anchor)
            blocks.append({"tag": f"h{level}", "html": f'<h{level} id="{anchor}">{inner}</h{level}>',
                           "text": plain(inner), "id": anchor})
            i += 1
            continue

        if line.startswith("```"):
            lang = line[3:].strip()
            code, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            if i == len(lines):
                raise PostError(f"{where}: code block never closed")
            cls = f' class="language-{esc(lang)}"' if lang else ""
            block("pre", f"<pre><code{cls}>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
            i += 1
            continue

        image = _IMAGE.match(line)
        if image:
            alt, src, caption = image.groups()
            if not alt:
                raise PostError(f"{where}: image {src} has no alt text")
            figcaption = f"<figcaption>{_inline(caption)}</figcaption>" if caption else ""
            block("figure", f'<figure class="post-figure" data-zoom>{img_tag(src, alt, FIGURE_SIZES)}{figcaption}</figure>')
            i += 1
            continue

        embed = _EMBED.match(line)
        if embed:
            kind = embed.group(1)
            block("video" if kind == "youtube" else "embed", render_embed(kind, embed.group(2), embed.group(3), where, slug))
            i += 1
            continue

        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            block("table", render_table(rows, where))
            continue

        if line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip())
                i += 1
            block("quote", render_quote(quote, where))
            continue

        for pattern, tag in ((_ORDERED, "ol"), (_BULLET, "ul")):
            if pattern.match(line):
                items = []
                while i < len(lines) and pattern.match(lines[i].strip()):
                    items.append("<li>" + _inline(pattern.sub("", lines[i].strip())) + "</li>")
                    i += 1
                block(tag, f"<{tag}>\n" + "\n".join(items) + f"\n</{tag}>")
                break
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not _BLOCK_START.match(lines[i].strip()):
                para.append(lines[i].strip())
                i += 1
            block("p", f"<p>{_inline(' '.join(para))}</p>")

    return blocks


def faq_entries(blocks: list[dict]) -> list[tuple[str, str]]:
    """Question and answer pairs from a `## FAQ` section of `###` questions."""
    entries: list[tuple[str, str]] = []
    in_faq, question, answer = False, None, []
    for b in blocks + [{"tag": "h2", "text": ""}]:
        if b["tag"] in ("h2", "h3") and question:
            entries.append((question, " ".join(answer)))
            question, answer = None, []
        if b["tag"] == "h2":
            in_faq = bool(FAQ_HEADING.match(b["text"]))
        elif in_faq and b["tag"] == "h3":
            question = b["text"]
        elif question and b["tag"] in ("p", "ul", "ol"):
            answer.append(b["text"])
    return entries


def citations(body: str) -> list[dict]:
    """Every outside source the post links, first mention first."""
    seen: dict[str, str] = {}
    for text, url in _INLINE_LINK.findall(_INLINE_CODE.sub(r"\1", body)):
        if url.startswith("http") and not url.startswith(OWN_URL_PREFIXES) and url not in seen:
            # An embed's link text is its kind ("!github"); its name is the address.
            seen[url] = url.split("://", 1)[1] if text.startswith("!") else plain(_inline(text))
    return [{"@type": "CreativeWork", "name": name, "url": url} for url, name in seen.items()]


# ── Front matter ────────────────────────────────────────────────────────────


def parse_front_matter(raw: str, slug: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        raise PostError(f"{slug}: no front matter")
    _, fm_block, body = raw.split("---", 2)

    fm: dict[str, str] = {}
    for line in fm_block.strip().split("\n"):
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip().strip('"').strip("'")

    missing = [k for k in REQUIRED_FRONT_MATTER if not fm.get(k)]
    if missing:
        raise PostError(f"{slug}: front matter missing {', '.join(missing)}")
    if fm.get("hero") and not fm.get("heroAlt"):
        raise PostError(f"{slug}: hero needs heroAlt")
    if fm["category"] not in CATEGORIES:
        raise PostError(f"{slug}: category {fm['category']!r} is not one of {', '.join(CATEGORIES)}. "
                        f"Topics belong in tags.")
    tags = tag_list(fm)
    if not 1 <= len(tags) <= MAX_TAGS or len(set(tags)) != len(tags):
        raise PostError(f"{slug}: tags must be 1-{MAX_TAGS} distinct entries, got {tags}")
    if any(t != t.lower() for t in tags):
        raise PostError(f"{slug}: tags are lowercase (proper nouns included), got {tags}")
    if fm.get("link"):
        host = urlparse(fm["link"]).hostname or ""
        if not fm["link"].startswith("https://") or not host:
            raise PostError(f"{slug}: link must be an https address, got {fm['link']!r}")
        if fm["link"].startswith(BASE):
            raise PostError(f"{slug}: link points at this site; a post published here is a normal post")
        if body.strip():
            raise PostError(f"{slug}: a link post is front matter only; its body would never be shown")
    fm.setdefault("audience", CATEGORIES[fm["category"]])
    if fm["audience"] not in BRIDGES:
        raise PostError(f"{slug}: audience must be one of {', '.join(BRIDGES)}")
    return fm, body.strip()


def tag_list(fm: dict[str, str]) -> list[str]:
    return [t.strip() for t in fm["tags"].split(",") if t.strip()]


def to_iso(date_text: str) -> str:
    for fmt in ("%b %d %Y", "%B %d %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_text, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    raise PostError(f"unparseable date: {date_text!r}")


# ── Page ────────────────────────────────────────────────────────────────────


def load_partial(name: str) -> str:
    """Inline a shared partial. A runtime fetch is not a crawlable link."""
    return (PARTIALS / name).read_text().strip()


def ld_script(data: dict) -> str:
    return f'<script type="application/ld+json">\n{json.dumps(data, ensure_ascii=False, indent=2)}\n</script>'


def structured_data(slug: str, fm: dict[str, str], blocks: list[dict], body: str,
                    images: list[str]) -> str:
    canonical = f"{BASE}/blog/{slug}"
    published = to_iso(fm["date"])
    posting = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "inLanguage": "en",
        "headline": fm["title"],
        "description": fm.get("description") or fm["excerpt"],
        "datePublished": published,
        "dateModified": to_iso(fm["updated"]) if fm.get("updated") else published,
        "articleSection": fm["category"],
        "wordCount": sum(len(b["text"].split()) for b in blocks),
        "author": {"@type": "Person", **AUTHOR},
        "publisher": {"@type": "Organization", "name": "Duct", "url": BASE},
        "image": images if len(images) > 1 else images[0],
        "mainEntityOfPage": canonical,
        "isPartOf": {"@type": "Blog", "name": "Duct Blog", "url": f"{BASE}/blog/"},
    }
    posting["keywords"] = tag_list(fm)
    sources = citations(body)
    if sources:
        posting["citation"] = sources

    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "inLanguage": "en",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{BASE}/blog/"},
            {"@type": "ListItem", "position": 3, "name": fm["title"], "item": canonical},
        ],
    }
    scripts = [ld_script(posting), ld_script(crumbs)]

    faq = faq_entries(blocks)
    if faq:
        scripts.append(ld_script({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "inLanguage": "en",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq
            ],
        }))
    return "\n".join(scripts)


def contents_list(fm: dict[str, str], blocks: list[dict]) -> str:
    sections = [b for b in blocks if b["tag"] == "h2"]
    if int(fm["readTime"]) < TOC_MIN_READ_MINUTES or len(sections) < TOC_MIN_SECTIONS:
        return ""
    items = "\n".join(f'<li><a href="#{b["id"]}">{esc(b["text"])}</a></li>' for b in sections)
    return f'<nav class="post-toc" aria-label="In this post">\n<p class="post-toc-title">In this post</p>\n<ol>\n{items}\n</ol>\n</nav>\n'


def render_bridge(audience: str) -> str:
    b = BRIDGES[audience]
    shot, media = b["shot"], "../assets/media"
    w, h = image_size(SITE / "assets" / "media" / f"{shot}.webp")
    srcset = ", ".join([f"{media}/{shot}-{v}.webp {v}w" for v in SRCSET_VARIANTS if v < w] + [f"{media}/{shot}.webp {w}w"])
    return f"""<section class="duct-bridge" aria-label="About Duct">
  <div class="duct-bridge-inner">
    <div class="duct-bridge-text">
      <p class="duct-bridge-headline">{b['headline']}</p>
      <p class="duct-bridge-body">{b['body']}</p>
      <p class="duct-bridge-actions">{b['actions']}</p>
    </div>
    <figure class="shot-frame duct-bridge-shot">
      <img src="{media}/{shot}.webp" srcset="{srcset}" sizes="(max-width: 860px) calc(100vw - 96px), 620px" decoding="async" width="{w}" height="{h}" loading="lazy" alt="{b['alt']}"/>
      <figcaption>{b['caption']}</figcaption>
    </figure>
  </div>
</section>"""


def render_page(slug: str, fm: dict[str, str], body: str, siblings: list[dict]) -> str:
    title = fm["title"]
    excerpt = fm["excerpt"]
    description = fm.get("description") or excerpt
    canonical = f"{BASE}/blog/{slug}"
    published = to_iso(fm["date"])
    blocks = render_markdown(body, slug)
    # The contents list goes after the opening, before the first section: the
    # answer a reader (or an answer engine) came for comes first.
    toc = contents_list(fm, blocks)
    first_h2 = next((i for i, b in enumerate(blocks) if b["tag"] == "h2"), len(blocks))
    body_html = "\n".join([b["html"] for b in blocks[:first_h2]] + ([toc.rstrip()] if toc else [])
                          + [b["html"] for b in blocks[first_h2:]])

    # Each post's card is drawn by scripts/build_og_images.mjs from the same
    # front matter and doubles as its cover on the index. A post without one
    # would share the site's generic card, which is what this used to do.
    og_file = OG_DIR / f"blog-{slug}.jpg"
    if not og_file.exists():
        raise PostError(f"{slug}: no card at site/assets/og/{og_file.name}. Run: node scripts/build_og_images.mjs")
    og_image = f"{BASE}/assets/og/{og_file.name}"

    hero_html = ""
    images = [og_image]
    if fm.get("hero"):
        hero_html = (f'<figure class="post-hero">{img_tag(fm["hero"], fm["heroAlt"], HERO_SIZES, eager=True)}'
                     "</figure>\n")
        images.insert(0, f"{BASE}/blog/{fm['hero']}")

    idx = next(i for i, p in enumerate(siblings) if p["slug"] == slug)
    prev_post = siblings[idx - 1] if idx > 0 else None
    next_post = siblings[idx + 1] if idx + 1 < len(siblings) else None

    # The header's "Blog" link was the only way back to the index from a post.
    nav_links = []
    if prev_post:
        nav_links.append(
            f'<a class="article-nav-prev" href="/blog/{prev_post["slug"]}">← {esc(prev_post["title"])}</a>'
        )
    nav_links.append('<a class="article-nav-all" href="/blog/">All posts</a>')
    if next_post:
        nav_links.append(
            f'<a class="article-nav-next" href="/blog/{next_post["slug"]}">{esc(next_post["title"])} →</a>'
        )
    nav_block = (
        '<nav class="article-nav" aria-label="More articles">\n' + "\n".join(nav_links) + "\n</nav>"
    )

    byline = [esc(fm["date"])]
    if fm.get("updated"):
        byline.append(f"Updated {esc(fm['updated'])}")
    byline += [f"{esc(fm['readTime'])} min read", f"By {AUTHOR['name']}"]

    full_title = fm.get("seoTitle") or f"{title} — Duct blog"
    modified = f'\n<meta property="article:modified_time" content="{to_iso(fm["updated"])}"/>' if fm.get("updated") else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link rel="icon" href="../assets/icon.svg" type="image/svg+xml"/>
<link rel="apple-touch-icon" href="../assets/apple-icon.svg"/>
<title>{esc(full_title)}</title>
<link rel="canonical" href="{canonical}"/>
<meta name="description" content="{esc(description)}"/>
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1"/>
<meta property="og:type" content="article"/>
<meta property="og:locale" content="en_US"/>
<meta property="og:url" content="{canonical}"/>
<meta property="og:title" content="{esc(full_title)}"/>
<meta property="og:description" content="{esc(excerpt)}"/>
<meta property="og:image" content="{og_image}"/>
<meta property="og:image:width" content="1200"/>
<meta property="og:image:height" content="630"/>
<meta property="og:site_name" content="Duct"/>
<meta property="article:author" content="{AUTHOR['name']}"/>
<meta property="article:section" content="{esc(fm['category'])}"/>
{chr(10).join(f'<meta property="article:tag" content="{esc(t)}"/>' for t in tag_list(fm))}
<meta property="article:published_time" content="{published}"/>{modified}
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{esc(full_title)}"/>
<meta name="twitter:description" content="{esc(excerpt)}"/>
<meta name="twitter:image" content="{og_image}"/>
<link rel="alternate" type="application/rss+xml" title="Duct Blog" href="/blog/feed.xml"/>
<link rel="stylesheet" href="../assets/duct.css"/>
<script src="../assets/config.js" defer></script>
{structured_data(slug, fm, blocks, body, images)}
<style>
#reading-progress {{
  position: fixed; top: 0; left: 0; width: 0%; height: 3px;
  background: var(--orange); z-index: 200; transition: width .1s linear;
}}
.post-author {{
  display: flex; gap: 20px; align-items: flex-start;
  max-width: 700px; margin: 48px auto 0; padding: 28px 24px;
  border-top: 1px solid var(--border);
}}
.post-author-avatar {{
  width: 64px; height: 64px; border-radius: 50%;
  object-fit: cover; flex-shrink: 0; background: var(--off);
  border: 1px solid var(--border);
}}
.post-author-name {{
  font-family: var(--serif); font-size: 18px; color: var(--navy);
  letter-spacing: -.2px; margin-bottom: 6px;
}}
.post-author-bio {{ font-size: 14px; font-weight: 300; color: var(--navy-3); line-height: 1.7; }}
.post-author-bio a {{ color: var(--orange); text-decoration: none; }}
.post-author-bio a:hover {{ text-decoration: underline; text-underline-offset: 3px; }}
.post-author-links {{ display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; }}
.post-author-links a {{
  font-size: 13px; font-weight: 500; color: var(--navy-2); text-decoration: none;
  border-bottom: 1px solid var(--border); padding-bottom: 1px; transition: border-color .2s;
}}
.post-author-links a:hover {{ border-color: var(--navy); }}
.article-nav {{
  display: flex; justify-content: space-between; gap: 24px;
  max-width: 700px; margin: 0 auto; padding: 32px 24px 64px;
}}
.article-nav a {{
  font-size: 14px; font-weight: 500; color: var(--navy-3);
  text-decoration: none; transition: color .2s; max-width: 46%;
}}
.article-nav a:hover {{ color: var(--navy); }}
.article-nav-next {{ margin-left: auto; text-align: right; }}
.article-nav-all {{ font-size: 13px; color: var(--navy-3); border-bottom: 1px solid var(--border); align-self: center; }}
.prose .post-tags {{ list-style: none; padding: 0; margin: 48px 0 0; display: flex; flex-wrap: wrap; gap: 8px; }}
.prose .post-tags li {{ font-size: 13px; font-weight: 500; color: var(--navy-2); background: var(--off); border: 1px solid var(--border); border-radius: 999px; padding: 3px 12px; margin: 0; }}
.post-hero {{ max-width: 700px; margin: 0 auto; padding: 0 24px; }}
.post-hero img {{ width: 100%; height: auto; display: block; border-radius: var(--r-lg); border: 1px solid var(--border); }}
.post-toc {{ margin: 0 0 40px; padding: 20px 24px; background: var(--off); border: 1px solid var(--border); border-radius: var(--r-lg); }}
.prose .post-toc-title {{ font-size: 12px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; color: var(--navy); margin: 0 0 10px; }}
.post-toc ol {{ margin: 0; padding-left: 20px; }}
.prose .post-toc li {{ font-size: 15px; margin-bottom: 4px; }}
.prose .post-toc a {{ border-bottom: none; }}
.prose h2, .prose h3 {{ scroll-margin-top: 88px; }}
.post-figure {{ margin: 36px 0; }}
.prose .post-figure img {{ height: auto; margin: 0; border: 1px solid var(--border); background: var(--white); }}
.post-figure figcaption, .post-quote figcaption {{ font-size: 13px; color: var(--navy-3); line-height: 1.6; margin-top: 10px; }}
.post-quote {{ margin: 36px 0; }}
.post-quote blockquote {{ margin: 0; }}
.post-quote blockquote p {{ font-family: var(--serif); font-size: 19px; line-height: 1.55; margin: 0 0 10px; }}
.post-quote figcaption {{ padding-left: 27px; }}
.post-table {{ margin: 28px 0 32px; overflow-x: auto; border: 1px solid var(--border); border-radius: var(--r); }}
.post-table table {{ width: 100%; border-collapse: collapse; font-size: 14px; line-height: 1.55; color: var(--navy-3); }}
.post-table th {{ text-align: left; font-weight: 600; color: var(--navy); background: var(--off); }}
.post-table th, .post-table td {{ padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: top; min-width: 120px; }}
.post-table tr:last-child td {{ border-bottom: none; }}
.post-table code {{ font-size: 12px; }}
.prose .post-embed {{
  display: flex; align-items: center; gap: 16px; margin: 28px 0; padding: 18px 20px;
  border: 1px solid var(--border); border-radius: var(--r-lg); background: var(--white);
  color: var(--navy-3); transition: border-color .15s, background .15s;
}}
.prose .post-embed:hover {{ border-color: var(--orange); background: var(--off); }}
.post-embed .ic {{ font-size: 28px; color: var(--navy); flex-shrink: 0; }}
.post-embed-body {{ display: flex; flex-direction: column; gap: 4px; min-width: 0; }}
.post-embed-title {{ font-size: 16px; color: var(--navy); }}
.post-embed-desc {{ font-size: 14px; font-weight: 300; line-height: 1.5; }}
.post-embed-host {{ margin-left: auto; font-size: 12px; color: var(--navy-3); flex-shrink: 0; }}
.post-video {{ position: relative; margin: 32px 0; aspect-ratio: 16 / 9; border-radius: var(--r-lg); overflow: hidden; background: var(--navy); }}
.prose .post-video-facade {{ display: block; position: absolute; inset: 0; border: none; color: #fff; }}
.prose .post-video-facade img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; margin: 0; border-radius: 0; }}
.post-video-facade::after {{ content: ""; position: absolute; inset: 0; background: linear-gradient(to top, rgba(13,15,26,.95) 0%, rgba(13,15,26,.75) 30%, rgba(13,15,26,0) 70%); }}
.post-video-play {{
  position: absolute; z-index: 1; left: 50%; top: 42%; transform: translate(-50%, -50%); width: 72px; height: 72px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; background: var(--orange); font-size: 30px; color: #fff;
  box-shadow: 0 8px 24px rgba(13,15,26,.35); transition: transform .15s;
}}
.post-video-facade:hover .post-video-play, .post-video-facade:focus-visible .post-video-play {{ transform: translate(-50%, -50%) scale(1.08); }}
.post-video-caption {{ position: absolute; z-index: 1; left: 0; right: 0; bottom: 0; padding: 20px 24px; display: flex; flex-direction: column; gap: 4px; }}
.post-video-title {{ font-family: var(--serif); font-size: 19px; line-height: 1.3; }}
.post-video-note {{ font-size: 13px; color: #c9ccd8; }}
.post-video iframe {{ width: 100%; height: 100%; border: 0; display: block; }}
@media (max-width: 640px) {{
  .post-video-title {{ font-size: 16px; }}
  .post-video-caption {{ padding: 14px 16px; }}
  .post-author {{ flex-direction: column; gap: 16px; }}
  .article-nav {{ flex-direction: column; gap: 16px; }}
  .article-nav a {{ max-width: 100%; }}
  .article-nav-next {{ text-align: left; margin-left: 0; }}
  .post-embed-host {{ display: none; }}
}}
</style>
</head>
<body>

<a href="#prose" class="skip-link">Skip to content</a>

<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM_ID}" height="0" width="0" style="display:none;visibility:hidden" title="Google Tag Manager"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->

<div id="reading-progress" role="progressbar" aria-label="Reading progress" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>

<!-- GENERATED FILE — edit blog/posts/{slug}.md and run scripts/build_blog.py -->
{load_partial('nav-blog.html')}

<header class="article-header">
<p class="tag">{esc(fm['category'])}</p>
<h1>{esc(title)}</h1>
<div class="article-meta">{' · '.join(byline)}</div>
</header>

<main>
{hero_html}<article id="prose" class="prose">
{body_html}
<ul class="post-tags" aria-label="Tags">{''.join(f'<li>{esc(t)}</li>' for t in tag_list(fm))}</ul>
</article>

<aside class="post-author" aria-label="About the author">
  <img class="post-author-avatar" src="https://github.com/5hirish.png" width="64" height="64" loading="lazy" alt="{AUTHOR['name']}"/>
  <div>
    <p class="post-author-name">{AUTHOR['name']}</p>
    <p class="post-author-bio">Product manager and engineer in Spain. I maintain <a href="{REPO_URL}" rel="noopener">Duct</a>, an open-source AI agent that reads across your product and growth stack. MIT licensed, runs on your own machine.</p>
    <div class="post-author-links">
      <a href="https://github.com/5hirish" rel="noopener">GitHub</a>
      <a href="https://x.com/5hirish" rel="noopener">X</a>
      <a href="https://youtube.com/@5hirish" rel="noopener">Ship with AI</a>
      <a href="https://shirishkadam.com" rel="noopener">Blog</a>
    </div>
  </div>
</aside>

{nav_block}
</main>

<!-- The closer is the product, not a pitch: the same bridge the tools pages
     end on, with a shot, so a post is not the one page on the site that ends
     in text alone. Which one depends on the post's audience. -->
{render_bridge(fm['audience'])}

{load_partial('footer-expanded.html')}

<script src="../assets/duct.js" defer></script>
<script src="../assets/duct-download.js" defer></script>
{VIDEO_SCRIPT if any(b["tag"] == "video" for b in blocks) else ""}<script>
(function () {{
  var bar = document.getElementById('reading-progress');
  window.addEventListener('scroll', function () {{
    var top = window.scrollY || document.documentElement.scrollTop;
    var height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
    var pct = height > 0 ? Math.round((top / height) * 100) : 0;
    bar.style.width = pct + '%';
    bar.setAttribute('aria-valuenow', pct);
  }}, {{ passive: true }});
}})();
</script>

</body>
</html>
"""


# Swaps a video facade for the privacy-enhanced player on the reader's click.
# Emitted only on posts that have a video; a modified click opens YouTube.
# The id is re-checked in the browser, not trusted because _YOUTUBE_ID wrote
# it: an attribute is page text by the time this runs (CodeQL flagged it on
# #255), and an id of any other shape falls through to the plain link.
VIDEO_SCRIPT = """<script>
(function () {
  var links = document.querySelectorAll('[data-youtube]');
  for (var i = 0; i < links.length; i++) {
    links[i].addEventListener('click', function (e) {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var id = this.getAttribute('data-youtube') || '';
      if (!/^[A-Za-z0-9_-]{11}$/.test(id)) return;
      e.preventDefault();
      var frame = document.createElement('iframe');
      frame.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(id) + '?autoplay=1&rel=0';
      frame.title = this.getAttribute('data-title');
      frame.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
      this.parentNode.replaceChild(frame, this);
    });
  }
})();
</script>
"""


def esc(text: str) -> str:
    return html.escape(text, quote=True)


# ── Blog index ──────────────────────────────────────────────────────────────

INDEX = OUT_DIR / "index.html"
INDEX_START = "<!-- blog-index:start (generated by scripts/build_blog.py from each post's front matter; edits here are overwritten) -->"
INDEX_END = "<!-- blog-index:end -->"

# Filters the grid by category, and keeps the choice in the URL so a filtered
# view can be shared. Without JavaScript the chips stay hidden and every post
# shows, which is the right fallback for a list this short.
INDEX_SCRIPT = """<script>
(function () {
  var bar = document.querySelector('.blog-filter');
  if (!bar) return;
  var chips = bar.querySelectorAll('[data-category]');
  var cards = document.querySelectorAll('.blog-grid > li');
  function apply(cat) {
    var known = false;
    for (var i = 0; i < chips.length; i++) {
      var on = chips[i].getAttribute('data-category') === cat;
      chips[i].setAttribute('aria-pressed', on ? 'true' : 'false');
      known = known || on;
    }
    if (!known) return apply('all');
    for (var j = 0; j < cards.length; j++) {
      cards[j].hidden = cat !== 'all' && cards[j].getAttribute('data-category') !== cat;
    }
  }
  bar.addEventListener('click', function (e) {
    var chip = e.target.closest && e.target.closest('[data-category]');
    if (!chip) return;
    var cat = chip.getAttribute('data-category');
    apply(cat);
    try { history.replaceState(null, '', cat === 'all' ? location.pathname : location.pathname + '?category=' + cat); } catch (err) {}
  });
  var match = /[?&]category=([a-z]+)/.exec(location.search);
  apply(match ? match[1] : 'all');
  bar.hidden = false;
})();
</script>"""


def render_index_block(posts: list[dict]) -> str:
    """The category filter and the card grid, newest first."""
    newest = sorted(posts, key=lambda p: p["iso"], reverse=True)
    counts = {c: sum(p["fm"]["category"] == c for p in posts) for c in CATEGORIES}
    chips = [f'<button type="button" class="blog-filter-chip" data-category="all" aria-pressed="true">All <span class="blog-filter-count">{len(posts)}</span></button>']
    chips += [f'<button type="button" class="blog-filter-chip" data-category="{c.lower()}" aria-pressed="false">{c} <span class="blog-filter-count">{n}</span></button>'
              for c, n in counts.items() if n]
    cards = []
    for i, p in enumerate(newest):
        fm, slug = p["fm"], p["slug"]
        delay = f' style="transition-delay:.{min(i, 5) * 8:02d}s"' if i else ""
        # A link post's card goes to where it was published, and says so
        # before the click rather than after it.
        link = fm.get("link")
        target = f'href="{esc(link)}" rel="noopener"' if link else f'href="/blog/{slug}"'
        where = f' on {esc(urlparse(link).hostname.removeprefix("www."))} ↗' if link else ""
        cards.append(
            f'<li data-category="{fm["category"].lower()}"><a {target} class="blog-card reveal"{delay}>\n'
            f'<img class="blog-card-img" src="../assets/og/blog-{slug}.jpg" width="1200" height="630" loading="lazy" alt=""/>\n'
            f'<div class="blog-card-body">\n<span class="tag">{esc(fm["category"])}</span>\n'
            f'<h2 class="blog-card-title">{esc(fm["title"])}</h2>\n'
            f'<p class="blog-card-excerpt">{esc(fm["excerpt"])}</p>\n'
            f'<div class="blog-card-meta"><span>{esc(fm["date"])}</span><span>{esc(fm["readTime"])} min read{where}</span></div>\n'
            f'</div>\n</a></li>'
        )
    return (f'{INDEX_START}\n<div class="blog-filter" role="group" aria-label="Filter posts by category" hidden>\n'
            + "\n".join(chips) + '\n</div>\n<ul class="blog-grid">\n' + "\n".join(cards)
            + f"\n</ul>\n{INDEX_SCRIPT}\n{INDEX_END}")


def render_index(posts: list[dict]) -> str:
    page = INDEX.read_text()
    start, end = page.find(INDEX_START), page.find(INDEX_END)
    if start < 0 or end < start:
        raise PostError("site/blog/index.html has lost its blog-index:start / blog-index:end markers")
    return page[:start] + render_index_block(posts) + page[end + len(INDEX_END):]


# ── Listings ────────────────────────────────────────────────────────────────


def listing_errors(posts: list[dict]) -> list[str]:
    """Where a post is missing from the three hand-kept listings.

    A post that renders but is in none of them is an orphan: the sitemap does
    not offer it, feed readers never see it, and the model-facing llms.txt
    does not know it exists. Each listing was forgotten at least once, so this
    is a check rather than a checklist line.
    """
    listings = {
        "site/sitemap.xml": ((SITE / "sitemap.xml").read_text(), "<loc>{url}</loc>"),
        "site/blog/feed.xml": ((OUT_DIR / "feed.xml").read_text(), "<link>{url}</link>"),
        "site/llms.txt": ((SITE / "llms.txt").read_text(), "({url})"),
    }
    errors = []
    for p in posts:
        url = f"{BASE}/blog/{p['slug']}"
        for name, (text, needle) in listings.items():
            if needle.format(url=url) not in text:
                errors.append(f"{p['slug']}: not in {name}")
    return errors


def fetch_thumbnails(posts: list[dict]) -> None:
    """Save each embedded video's thumbnail beside its post, once.

    The only network step in this script, and never part of --check: the copy
    is committed, so the page and CI read it from the tree. curl rather than
    urllib, because behind the agent sandbox's proxy urllib's reads of larger
    bodies come back truncated.
    """
    for p in posts:
        for line in p["body"].split("\n"):
            embed = _EMBED.match(line.strip())
            video = embed and embed.group(1) == "youtube" and _YOUTUBE_ID.match(embed.group(2))
            if not video:
                continue
            target = OUT_DIR / youtube_thumbnail(p["slug"], video.group(1))
            if target.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            for size in ("maxresdefault", "hqdefault"):  # not every video has the first
                url = f"https://i.ytimg.com/vi/{video.group(1)}/{size}.jpg"
                if subprocess.run(["curl", "-sfL", "--max-time", "20", "-o", str(target), url]).returncode == 0:
                    print(f"saved {url} to site/blog/{youtube_thumbnail(p['slug'], video.group(1))}")
                    break
            else:
                raise PostError(f"{p['slug']}: could not fetch a thumbnail for video {video.group(1)}")


# ── Driver ──────────────────────────────────────────────────────────────────


def load_posts() -> list[dict]:
    posts = []
    for path in sorted(POSTS.glob("*.md")):
        slug = path.stem
        fm, body = parse_front_matter(path.read_text(), slug)
        posts.append({"slug": slug, "fm": fm, "body": body, "title": fm["title"],
                      "iso": to_iso(fm["date"]), "link": fm.get("link", "")})
    # Oldest first, so "next article" moves forward in time.
    posts.sort(key=lambda p: p["iso"])
    return posts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any generated file is missing or stale")
    parser.add_argument("--fetch-thumbnails", action="store_true",
                        help="save missing video thumbnails beside their posts (network)")
    args = parser.parse_args()

    try:
        posts = load_posts()
        if args.fetch_thumbnails:
            fetch_thumbnails(posts)
        # Link posts are cards on the index only: no page, no neighbours.
        own = [p for p in posts if not p["link"]]
        pages = {f'{p["slug"]}.html': render_page(p["slug"], p["fm"], p["body"], own) for p in own}
        pages["index.html"] = render_index(posts)
    except PostError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stale = []
    for name, content in pages.items():
        target = OUT_DIR / name
        if args.check:
            if not target.exists() or target.read_text() != content:
                stale.append(name)
        else:
            target.write_text(content)
            print(f"wrote site/blog/{name} ({len(content):,} bytes)")

    failed = False
    if stale:
        print("ERROR: generated blog pages are stale: " + ", ".join(stale), file=sys.stderr)
        print("Run: python3 scripts/build_blog.py", file=sys.stderr)
        failed = True
    for error in listing_errors(own):
        print(f"ERROR: {error}", file=sys.stderr)
        failed = True
    if args.check and not failed:
        linked = len(posts) - len(own)
        print(f"All {len(own)} posts and the blog index are up to date and listed"
              + (f", with {linked} link post{'s' * (linked != 1)}." if linked else "."))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
