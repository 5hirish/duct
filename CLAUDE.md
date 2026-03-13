# Duct — Claude Code instructions

Static marketing site for [getduct.ai](https://getduct.ai). Pure HTML/CSS/JS.

## Site strategy

Two content types, two jobs:
- **Landing pages** (`for-*.html`) — paid ad experiments. Each page targets a specific audience/solution angle. Fast to create, easy to A/B via URL. Goal: validate conversion before investing in a channel or audience.
- **Blog** (`blog/posts/`) — organic SEO. Written for keyword clusters, not just announcements. Goal: compound traffic from search.

When adding either, ask: *what's the hypothesis being tested?* Name it in a `<!-- EXPERIMENT: hypothesis here -->` comment at the top of the file's `<body>`.

When creating a variant LP for the same audience, name it `for-<audience>-v2.html` etc. Stale variants that lost should be removed, not left to accumulate.

## Stack constraints

- **NO build tools.** No npm, Vite, Webpack, Rollup, or any package manager.
- No frameworks (React, Vue, Astro, etc.). Not even Alpine.
- If a task seems to need a build step, ask first — the answer is almost always no.
- JavaScript is vanilla, ES5-compatible where possible.

## Local dev

```
python3 -m http.server 8080
```

Then open `http://localhost:8080/`. The server is required for blog posts — `fetch()` calls for `.md` files fail on `file://`.

Live Server (VS Code extension, port 5500) also works — see `.vscode/settings.json`.

## URL → file mapping

| Production URL | File |
|---|---|
| `https://getduct.ai/` | `index.html` |
| `https://getduct.ai/for-product-intelligence` | `for-product-intelligence.html` |
| `https://getduct.ai/for-organic-growth` | `for-organic-growth.html` |
| `https://getduct.ai/blog` | `blog/index.html` |
| `https://getduct.ai/blog/post.html?slug=SLUG` | `blog/post.html` (JS-rendered from `blog/posts/<slug>.md`) |

## Shared assets

| File | Purpose |
|---|---|
| `assets/duct.css` | All brand styles — edit this, not inline styles |
| `assets/duct.js` | GTM init, scroll reveal, nav shadow, `submitForm()` |
| `assets/config.js` | `DUCT_CONFIG.gtm` — GTM container ID only |

- Never duplicate shared styles or scripts in page files.
- `assets/config.js` must load **before** `assets/duct.js`.
- Blog pages use `../assets/` (not `assets/`).

## Page `<head>` checklist

Every HTML page must have:
- `<link rel="canonical" href="https://getduct.ai/EXACT-PATH"/>` — production URL, no trailing slash
- `<meta name="description">` — 140–160 characters
- `<meta name="robots" content="index, follow"/>`
- Open Graph: `og:type`, `og:url`, `og:title`, `og:description`, `og:image`, `og:site_name`
- Twitter: `twitter:card`, `twitter:title`, `twitter:description`, `twitter:site`, `twitter:image`
- `<link rel="stylesheet" href="assets/duct.css"/>` (or `../assets/duct.css` for blog/)
- `<script src="assets/config.js"></script>` then `<script src="assets/duct.js" defer></script>`
- GTM noscript `<iframe>` immediately after `<body>` open tag

## Google Forms (lead capture)

```html
<button class="btn btn-orange btn-lg"
  data-form-url="https://docs.google.com/forms/d/e/FORM_ID/formResponse"
  data-entry-id="entry.FIELD_ID"
  onclick="submitForm('INPUT_ID', this)">Get early access →</button>
```

Copy `data-form-url` and `data-entry-id` from `for-product-intelligence.html` unless the new page needs its own form. No `<form>` element — the pattern uses a plain `<input>` + `<button>`.

## Adding a new landing page variant

See skill: `/new-page`. Quick version:
1. Copy `for-product-intelligence.html` → `for-NEW-AUDIENCE.html`
2. Update `<title>`, canonical, nav subtitle, hero copy, audience cards
3. Add to `sitemap.xml` with `<priority>0.9</priority>`

## Adding a blog post

See skill: `/add-blog-post`. Posts are Markdown files in `blog/posts/<slug>.md` with YAML front matter. Required keys: `title`, `date`, `author`, `category`, `excerpt`, `readTime`.

## Sitemap

`sitemap.xml` at repo root. Add an entry for every new page or post:
- Landing pages: `<priority>0.9</priority>`, `<changefreq>weekly</changefreq>`
- Blog posts: `<priority>0.7</priority>`, `<changefreq>monthly</changefreq>`, URL uses `?slug=SLUG`

## Deploy

Push `main`. Netlify/Vercel/Cloudflare Pages auto-deploys. No build command. Publish directory: `/` (repo root). The platform strips `.html` from URLs automatically.

## Performance constraints

Every page must load fast on mobile. This means:
- No web fonts beyond the system stack already in `duct.css`
- Images: WebP only, explicit `width`/`height` attributes, `loading="lazy"` below the fold
- No third-party scripts except GTM (already deferred)
- Hero must be fully legible at 375px with no horizontal scroll

## Conversion hygiene

- Every LP needs exactly one primary CTA above the fold and one at the bottom
- CTA button copy must be action-specific (`Get early access →`, `Reserve your spot →`) — never "Submit" or "Learn more"
- Every CTA must have trust signals nearby: free/no credit card/unsubscribe copy
- The `.hero-footnote` anchors who this is *for* — keep it honest to reduce wrong-fit signups

## What NOT to do

- Do not create `package.json`, `node_modules`, or any npm tooling
- Do not create `.env` files — there are no secrets in this repo
- Do not hardcode the GTM ID in new files — source it from `DUCT_CONFIG.gtm` in `assets/config.js`
- Do not add page-specific styles to `assets/duct.css` — use an inline `<style>` block in the page file (see `for-organic-growth.html` lines 30–59 for the accent colour override pattern)
