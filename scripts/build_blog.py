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
Deliberately small: h2, paragraphs, ordered and bullet lists, bold, links.
Anything else — code fences, tables, images, blockquotes, h1, h3+ — raises
rather than rendering wrong. A generator that silently mangles a construct is
worse than one that refuses, because nobody reads generated output.

Usage
-----
    python3 scripts/build_blog.py            # write site/blog/<slug>.html
    python3 scripts/build_blog.py --check    # exit 1 if the tree is stale
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
POSTS = SITE / "blog" / "posts"
OUT_DIR = SITE / "blog"
PARTIALS = SITE / "partials"

BASE = "https://getduct.ai"
OG_IMAGE = f"{BASE}/assets/og-image.png"
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

REQUIRED_FRONT_MATTER = ("title", "date", "author", "category", "excerpt", "readTime")


class PostError(Exception):
    """A post the generator refuses to render, with the reason."""


# ── Markdown ────────────────────────────────────────────────────────────────

_INLINE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_INLINE_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ORDERED = re.compile(r"^\d+\.\s+")
_BULLET = re.compile(r"^[-*]\s+")
_BLOCK_START = re.compile(r"^(#|\d+\.\s|[-*]\s|```|\||>)")


def _inline(text: str) -> str:
    """Escape, then re-introduce only the inline markup we support.

    Escaping first is what makes this safe: a post can contain `<` or `&`
    without the generator emitting broken markup or, worse, live HTML.
    """
    out = html.escape(text, quote=False)
    out = _INLINE_LINK.sub(
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', out
    )
    out = _INLINE_BOLD.sub(r"<strong>\1</strong>", out)
    return out


def render_markdown(body: str, slug: str) -> str:
    """Render the supported subset, refusing anything outside it."""
    blocks: list[str] = []
    lines = body.split("\n")
    i = 0

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        if not line:
            i += 1
            continue

        for token, why in (
            ("```", "code fence"),
            ("|", "table"),
            ("![", "image"),
            (">", "blockquote"),
        ):
            if line.startswith(token):
                raise PostError(
                    f"{slug}: unsupported Markdown ({why}) at line {i + 1}. "
                    f"Extend render_markdown() in scripts/build_blog.py before using it."
                )

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level != 2:
                raise PostError(
                    f"{slug}: h{level} at line {i + 1}. Posts use h2 only — the page "
                    f"title is the h1, and skipping levels breaks the outline."
                )
            blocks.append(f"<h2>{_inline(line[level:].strip())}</h2>")
            i += 1
            continue

        if _ORDERED.match(line):
            items = []
            while i < len(lines) and _ORDERED.match(lines[i].strip()):
                text = _ORDERED.sub("", lines[i].strip())
                items.append("<li>" + _inline(text) + "</li>")
                i += 1
            blocks.append("<ol>\n" + "\n".join(items) + "\n</ol>")
            continue

        if _BULLET.match(line):
            items = []
            while i < len(lines) and _BULLET.match(lines[i].strip()):
                text = _BULLET.sub("", lines[i].strip())
                items.append("<li>" + _inline(text) + "</li>")
                i += 1
            blocks.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue

        para = []
        while i < len(lines) and lines[i].strip() and not _BLOCK_START.match(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        blocks.append(f"<p>{_inline(' '.join(para))}</p>")

    return "\n".join(blocks)


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
    return fm, body.strip()


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


def render_page(slug: str, fm: dict[str, str], body_html: str, siblings: list[dict]) -> str:
    title = fm["title"]
    excerpt = fm["excerpt"]
    canonical = f"{BASE}/blog/{slug}"
    published = to_iso(fm["date"])

    ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": excerpt,
        "datePublished": published,
        "dateModified": published,
        "articleSection": fm["category"],
        "author": {"@type": "Person", **AUTHOR},
        "publisher": {"@type": "Organization", "name": "Duct", "url": BASE},
        "image": OG_IMAGE,
        "mainEntityOfPage": canonical,
    }

    idx = next(i for i, p in enumerate(siblings) if p["slug"] == slug)
    prev_post = siblings[idx - 1] if idx > 0 else None
    next_post = siblings[idx + 1] if idx + 1 < len(siblings) else None

    nav_links = []
    if prev_post:
        nav_links.append(
            f'<a class="article-nav-prev" href="/blog/{prev_post["slug"]}">← {esc(prev_post["title"])}</a>'
        )
    if next_post:
        nav_links.append(
            f'<a class="article-nav-next" href="/blog/{next_post["slug"]}">{esc(next_post["title"])} →</a>'
        )
    nav_block = (
        f'<nav class="article-nav" aria-label="More articles">\n' + "\n".join(nav_links) + "\n</nav>"
        if nav_links
        else ""
    )

    full_title = f"{title} — Duct Insights"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link rel="icon" href="../assets/icon.svg" type="image/svg+xml"/>
<link rel="apple-touch-icon" href="../assets/apple-icon.svg"/>
<title>{esc(full_title)}</title>
<link rel="canonical" href="{canonical}"/>
<meta name="description" content="{esc(excerpt)}"/>
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1"/>
<meta property="og:type" content="article"/>
<meta property="og:url" content="{canonical}"/>
<meta property="og:title" content="{esc(full_title)}"/>
<meta property="og:description" content="{esc(excerpt)}"/>
<meta property="og:image" content="{OG_IMAGE}"/>
<meta property="og:site_name" content="Duct"/>
<meta property="article:author" content="{AUTHOR['name']}"/>
<meta property="article:section" content="{esc(fm['category'])}"/>
<meta property="article:published_time" content="{published}"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{esc(full_title)}"/>
<meta name="twitter:description" content="{esc(excerpt)}"/>
<meta name="twitter:image" content="{OG_IMAGE}"/>
<link rel="alternate" type="application/rss+xml" title="Duct Blog" href="/blog/feed.xml"/>
<link rel="stylesheet" href="../assets/duct.css"/>
<script src="../assets/config.js" defer></script>
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=2)}
</script>
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
@media (max-width: 640px) {{
  .post-author {{ flex-direction: column; gap: 16px; }}
  .article-nav {{ flex-direction: column; gap: 16px; }}
  .article-nav a {{ max-width: 100%; }}
  .article-nav-next {{ text-align: left; margin-left: 0; }}
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
<div class="article-meta">{esc(fm['date'])} · {esc(fm['readTime'])} min read · By {AUTHOR['name']}</div>
</header>

<main>
<article id="prose" class="prose">
{body_html}
</article>

<aside class="post-author" aria-label="About the author">
  <img class="post-author-avatar" src="https://github.com/5hirish.png" width="64" height="64" loading="lazy" alt="{AUTHOR['name']}"/>
  <div>
    <p class="post-author-name">{AUTHOR['name']}</p>
    <p class="post-author-bio">Product manager and engineer in Valencia. I maintain <a href="https://github.com/5hirish/duct" rel="noopener">Duct</a>, an open-source AI agent that reads across your product and growth stack. MIT licensed, runs on your own machine.</p>
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

{load_partial('cta-blog.html')}

{load_partial('footer-expanded.html')}

<script src="../assets/duct.js" defer></script>
<script>
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


def esc(text: str) -> str:
    return html.escape(text, quote=True)


# ── Driver ──────────────────────────────────────────────────────────────────


def build() -> dict[str, str]:
    posts = []
    for path in sorted(POSTS.glob("*.md")):
        slug = path.stem
        fm, body = parse_front_matter(path.read_text(), slug)
        posts.append({"slug": slug, "fm": fm, "body": body, "title": fm["title"],
                      "iso": to_iso(fm["date"])})

    # Oldest first, so "next article" moves forward in time.
    posts.sort(key=lambda p: p["iso"])

    return {
        f'{p["slug"]}.html': render_page(p["slug"], p["fm"], render_markdown(p["body"], p["slug"]), posts)
        for p in posts
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any generated file is missing or stale")
    args = parser.parse_args()

    try:
        pages = build()
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

    if args.check:
        if stale:
            print("ERROR: generated blog pages are stale: " + ", ".join(stale), file=sys.stderr)
            print("Run: python3 scripts/build_blog.py", file=sys.stderr)
            return 1
        print(f"All {len(pages)} generated blog pages are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
