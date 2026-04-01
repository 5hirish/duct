# Duct Site — Claude Code instructions

Static marketing site for [getduct.ai](https://getduct.ai). Pure HTML/CSS/JS.

## Site strategy

Two content types, two jobs:
- **Landing pages** (`for-*.html`) — paid ad experiments. Each page targets a specific audience or solution angle. Fast to create, easy to A/B by URL. Goal: validate conversion before investing in a channel or audience.
- **Blog** (`blog/posts/`) — organic SEO. Written for keyword clusters, not just announcements. Goal: compound traffic from search.

When adding either, ask: *what's the hypothesis being tested?* Put it in a `<!-- EXPERIMENT: ... -->` comment near the top of `<body>`.

## Stack constraints

- **NO build tools.** No npm, Vite, Webpack, Rollup, or package manager setup.
- No frameworks (React, Vue, Astro, Alpine, etc.).
- JavaScript should stay vanilla and ES5-compatible where practical.

## Local dev

```bash
python3 -m http.server 8080 --directory site
```

Then open `http://localhost:8080/`.

## URL → file mapping

| Production URL | File |
|---|---|
| `https://getduct.ai/` | `site/index.html` |
| `https://getduct.ai/for-product-intelligence` | `site/for-product-intelligence.html` |
| `https://getduct.ai/for-organic-growth` | `site/for-organic-growth.html` |
| `https://getduct.ai/for-paid-ads` | `site/for-paid-ads.html` |
| `https://getduct.ai/blog` | `site/blog/index.html` |
| `https://getduct.ai/blog/post.html?slug=SLUG` | `site/blog/post.html` |

## Shared assets

| File | Purpose |
|---|---|
| `site/assets/duct.css` | All brand styles |
| `site/assets/duct.js` | GTM init, scroll reveal, nav shadow, `submitForm()` |
| `site/assets/config.js` | `DUCT_CONFIG.gtm` only |

- Inside `site/` HTML files, root-level pages use `assets/`.
- Blog files under `site/blog/` use `../assets/`.
- `config.js` must load before `duct.js`.

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

## New landing page variant

1. Copy `site/for-product-intelligence.html` to a new `site/for-*.html` file.
2. Update title, canonical, nav subtitle, hero copy, and audience cards.
3. Add the new page to `site/sitemap.xml`.

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
