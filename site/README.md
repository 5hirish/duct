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
python3 -m http.server 8090 --directory site
```

Then open `http://localhost:8090/`.

## Automated QA (Playwright)

Smoke tests cover the highest-risk user flows and routing behavior:

- homepage and primary navigation links
- clean URL routing for landing pages
- blog list to post navigation
- blog post rendering for valid, missing, and invalid `slug` values

Install dependencies and browser once:

```bash
npm --prefix site ci
npm --prefix site run test:e2e:install
```

Run smoke tests:

```bash
npm --prefix site run test:e2e
```

Debug options:

```bash
npm --prefix site run test:e2e:headed
npm --prefix site run test:e2e:ui
```

In CI, the `Site Checks` workflow runs these smoke tests and uploads Playwright artifacts on failures.

## Social preview

`assets/og-image.png` is the `og:image` for all 23 pages. It is generated, not
hand-drawn — edit `scripts/social/template.html` and re-run:

```bash
node scripts/social/render.mjs
```

That also writes `.github/social-preview.png`, the GitHub repository card, which
has to be uploaded by hand at Settings → Social preview.

## Conventions

- pure HTML/CSS/JS only
- no build tools
- shared CSS and JS stay in `assets/`
- blog post markdown lives in `blog/posts/`

## Agent guidance

Conventions for this directory: [`AGENTS.md`](AGENTS.md) — canonical links,
shared assets, sitemap entries and GTM handling all have hard rules there.
`CLAUDE.md` is a symlink to the same file.
