# Landing pages and blog posts

This file used to restate the `site/` conventions in full. It drifted: it told
you to write `https://getduct.ai/blog/post.html?slug=SLUG` as the canonical and
the sitemap entry for a blog post, while the site itself uses the extensionless
`https://getduct.ai/blog/post?slug=SLUG` in `sitemap.xml`, in `blog/index.html`,
and in the canonical `blog/post.html` sets at runtime — and CI rejects any
canonical containing `.html`. An agent following this file wrote a URL the site
does not use.

That is the argument against a second copy, so this is a pointer now:

- **[`site/AGENTS.md`](../../site/AGENTS.md)** — canonical URLs, the `<head>`
  checklist, asset paths and load order, sitemap entries, Google Forms markup,
  GTM placement, the demo-variant pattern, and how to add a page or a post.
  Everything CI enforces is here.
- **[`STYLE.md`](../../STYLE.md)** — the part CI cannot check: description
  lengths, JSON-LD types, where page-specific CSS goes, and how conservative the
  JavaScript stays.

Both are tool-neutral, so Cursor and any other agent read the same rules Claude
does. Add new `site/` conventions to those files, not to this one.
