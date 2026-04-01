# Duct Site

This directory contains the static marketing site for [getduct.ai](https://getduct.ai).

## What lives here

- landing pages: `for-*.html`
- home page: `index.html`
- blog: `blog/`
- shared assets: `assets/`
- marketing sitemap: `sitemap.xml`
- robots file: `robots.txt`

## Local dev

```bash
python3 -m http.server 8080 --directory site
```

Then open `http://localhost:8080/`.

## Conventions

- pure HTML/CSS/JS only
- no build tools
- shared CSS and JS stay in `assets/`
- blog post markdown lives in `blog/posts/`

## Agent guidance

- Cursor subdirectory instructions: `site/AGENTS.md`
- Claude Code subdirectory instructions: `site/CLAUDE.md`
