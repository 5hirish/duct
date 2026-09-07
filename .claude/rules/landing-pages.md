# Landing pages and blog posts

This file used to restate the `site/` conventions in full, and it drifted twice
over the same fact. First it told you to write
`https://getduct.ai/blog/post.html?slug=SLUG` as a post's canonical and sitemap
entry, while the site used the extensionless `…/blog/post?slug=SLUG` and CI
rejected any canonical containing `.html`. Then posts stopped being rendered in
the browser at all: `scripts/build_blog.py` pre-renders each one to
`https://getduct.ai/blog/<slug>`, and `blog/post.html` is a `noindex` redirect
shim kept only for links published before the change. Both times, an agent
following this file wrote a URL the site does not serve.

That is the argument against a second copy, so this is a pointer now:

- **[`site/AGENTS.md`](../../site/AGENTS.md)** — canonical URLs, the `<head>`
  checklist, asset paths and load order, sitemap entries, Google Forms markup,
  GTM placement, the demo-variant pattern, and how to add a page or a post.
  Everything CI enforces is here.
- **[`site/DESIGN.md`](../../site/DESIGN.md)** — design & voice: the visual
  system and its signature moves, the accent-variant rule, contrast rules for
  the brand orange, the copy voice with its two signature structures, and the
  review checklist for a new page.
- **[`STYLE.md`](../../STYLE.md)** — the part CI cannot check: description
  lengths, JSON-LD types, where page-specific CSS goes, and how conservative the
  JavaScript stays.

Both are tool-neutral, so Cursor and any other agent read the same rules Claude
does. Add new `site/` conventions to those files, not to this one.
