# Duct Site — agent instructions

Static marketing site for [getduct.ai](https://getduct.ai). Pure HTML/CSS/JS.

## Site strategy

Two content types, two jobs:
- **Landing pages** (`for-*.html`) — paid ad experiments. Each page targets a specific audience or solution angle. Fast to create, easy to A/B by URL. Goal: validate conversion before investing in a channel or audience.
- **Blog** (`blog/posts/`) — organic SEO. Written for keyword clusters, not just announcements. Goal: compound traffic from search.

When adding either, ask: *what's the hypothesis being tested?* Put it in a `<!-- EXPERIMENT: ... -->` comment near the top of `<body>`.

**[`DESIGN.md`](DESIGN.md) is the design & voice companion to this file** —
the visual system as built (tokens, signature moves, section rhythm), the
accent-variant rule, the contrast rules for the brand orange, the copy voice
codified from the site's best lines, landing-page craft, and a
close-on-touch gap list. This file stays the home of the mechanical rules CI
enforces. Read both before building a page.

## Stack constraints

- **NO build tools.** No npm, Vite, Webpack, Rollup, or package manager setup.
- No frameworks (React, Vue, Astro, Alpine, etc.).
- JavaScript should stay vanilla and ES5-compatible where practical.

## Local dev

```bash
python3 -m http.server 8090 --directory site
```

Then open `http://localhost:8090/`.

For Cloudflare-style routing (extensionless URLs), use `python3 dev_server.py
--port 8090` from inside `site/` — the VS Code task **Serve site on :8090** does
exactly that. Only one process can bind 8090; `Address already in use` means a
previous `dev_server.py` is still running, so stop it rather than picking
another port (the tests assume 8090).

## URL → file mapping

| Production URL | File |
|---|---|
| `https://getduct.ai/` | `site/index.html` |
| `https://getduct.ai/for-product-intelligence` | `site/for-product-intelligence.html` |
| `https://getduct.ai/for-organic-growth` | `site/for-organic-growth.html` |
| `https://getduct.ai/for-paid-ads` | `site/for-paid-ads.html` |
| `https://getduct.ai/doctrine` | `site/doctrine.html` |
| `https://getduct.ai/blog/` | `site/blog/index.html` |
| `https://getduct.ai/blog/post?slug=SLUG` | `site/blog/post.html` |

## Shared assets

| File | Purpose |
|---|---|
| `site/assets/duct.css` | All brand styles |
| `site/assets/duct.js` | GTM init, scroll reveal, nav shadow, `submitForm()` |
| `site/assets/config.js` | `DUCT_CONFIG.gtm` only |
| `site/assets/demo.css` | All shared interactive demo CSS (~800 lines) |
| `site/assets/demo.js` | Shared demo JS engine (state machine, navigation, modal, hash routing) |
| `site/assets/demo-paid-ads.js` | Paid Ads variant data + Engine A fill override |
| `site/assets/demo-product.js` | Product Intelligence variant data |
| `site/assets/demo-organic.js` | Organic Growth variant data |

- Inside `site/` HTML files, root-level pages use `assets/`.
- Blog files under `site/blog/` use `../assets/`.
- `config.js` must load before `duct.js`.

## Interactive demo pattern

Each `for-*.html` landing page that has a demo includes:

```html
<!-- in <head>, after duct.css -->
<link rel="stylesheet" href="assets/demo.css"/>
```

```html
<!-- at end of <body>, before duct.js -->
<script src="assets/demo-<variant>.js"></script>
<script src="assets/demo.js"></script>
<script src="assets/duct.js" defer></script>
```

The per-variant file (`demo-<variant>.js`) sets `window.DUCT_DEMO_CONFIG` with:

```js
window.DUCT_DEMO_CONFIG = {
  cfg: {
    min: 2,                    // minimum platforms before "Next" enables
    src: { PlatformName: 'API label', ... },
    defs: { metricKey: { hero, fmt, label, bar, ths, hide }, ... },
    cross: { metricKey: [...] or {level,pill,title,body,ownerName,assignee,followUp}, ... },
    kpiKeys: ['key1', 'key2', ...],
    kpiDefs: { key1: { fmt: 'p1' }, key2: { fmt: 'k', sum: true }, ... },
    defaultMetric: 'key1',
    defaultPlatforms: ['Plat1', 'Plat2'],
    sparkColor: '#hexcolor'    // optional, defaults to #2563eb
  },
  data: D,                     // { PlatformName: { metricKey: { hero, k, r, s, sp, u }, ... } }
  fill: fillFn,                // optional: custom fill function (paid-ads only)
  minHint: 2                   // optional: hide #plat-hint when >= N platforms selected
};
```

`kpiDefs[key].sum: true` → sum across platforms; omit for average.
`cross[metricKey]` accepts either an array `[level, pill, title, body, ownerName, assignee, followUp]` or a named-key object (both normalised internally).

### Adding a new demo variant

1. Create `site/assets/demo-for-x.js` with `window.DUCT_DEMO_CONFIG`.
2. Copy an existing `for-*.html`, update meta/hero/sections.
3. Swap demo step HTML (plat-grid buttons, metric-grid cards, analyzing lines, KPI chip IDs).
4. `<link demo.css>` in head; `<script demo-for-x.js>` + `<script demo.js>` at body end.
5. Add to `sitemap.xml`.

## Discoverability files

| File | Purpose |
|---|---|
| `site/robots.txt` | Crawl policy. Names AI agents explicitly because vendors split training and search into separate bots (`GPTBot` vs `OAI-SearchBot`, `ClaudeBot` vs `Claude-SearchBot`); a bare `User-agent: *` leaves that ambiguous. |
| `site/sitemap.xml` | Every indexable page. A new page is not done until it is here. Bump `lastmod` only on pages the change actually touched. |
| `site/blog/feed.xml` | RSS. Hand-maintained: add an `<item>` with every new post. CI fails if it is missing, empty, or carries an off-domain `<link>`. |
| `site/llms.txt` | Plain-text site map for models. Low crawler uptake in practice, cheap to keep correct, and the place the open-source framing has to be right. |
| `site/_headers` | `Link:` discovery headers plus the RSS content type Cloudflare would otherwise get wrong. |

JSON-LD is validated by `check-pages.py`: every `application/ld+json` block must
parse and carry an `@type`. A malformed block is dropped silently by every
consumer, so the page keeps rendering while its structured data is simply gone.

The home page carries `SoftwareApplication` **and** `SoftwareSourceCode`. The
second is what tells an answer engine the project is open source; the first
alone does not. `Organization.sameAs` and `Person.sameAs` are what tie the site,
the repo and the maintainer into one entity rather than three.

## Canonical URLs

**Extensionless, always.** `.github/scripts/check-pages.py` fails any canonical
containing `.html`, and `site/sitemap.xml` must use the same form or the two
disagree about what the page's address is.

| Page | Canonical |
|---|---|
| Root-level landing page | `https://getduct.ai/for-paid-ads` |
| Blog index | `https://getduct.ai/blog/` |
| Blog post | `https://getduct.ai/blog/post?slug=SLUG` |

`blog/post.html` sets its own canonical at runtime from the slug (see its inline
script) — do not hardcode one there. Every other page hardcodes it in `<head>`.

## Page `<head>` checklist

Every HTML page must have:
- canonical
- description
- robots
- OG tags
- Twitter tags
- shared stylesheet
- `config.js` then `duct.js`
- GTM noscript iframe immediately after `<body>`

## Google Forms

```html
<button class="btn btn-orange btn-lg"
  data-form-url="https://docs.google.com/forms/d/e/FORM_ID/formResponse"
  data-entry-id="entry.FIELD_ID"
  onclick="submitForm('INPUT_ID', this)">Get early access →</button>
```

Copy the form attributes from `site/for-product-intelligence.html` unless the page needs a distinct form. Do not add a `<form>` element.

## New landing page variant (no demo)

1. Copy `site/for-product-intelligence.html` to a new `site/for-*.html` file.
2. Update title, canonical, nav subtitle, hero copy, and audience cards.
3. Add the new page to `site/sitemap.xml`.

## New landing page variant (with demo)

Follow the **Adding a new demo variant** instructions above.

## New blog post

Posts live in `site/blog/posts/<slug>.md` with required front matter:
- `title`
- `date`
- `author`
- `category`
- `excerpt`
- `readTime`

## Deploy

Publish directory: `site/`.

## What not to do

- Do not add npm tooling.
- Do not create `.env` files.
- Do not hardcode the GTM ID in page JavaScript.
- Do not put page-specific styles into `site/assets/duct.css`; use an inline `<style>` block when needed.
