---
description: Conventions for Duct landing pages and shared assets
globs: ["*.html", "assets/**", "blog/**"]
---

## Canonical links

- Every `*.html` file must have `<link rel="canonical" href="https://getduct.ai/PATH"/>`.
- Use the clean URL (no `.html` extension) for root-level pages: `/for-organic-growth`, not `/for-organic-growth.html`.
- Blog post pages use the query-string form: `https://getduct.ai/blog/post.html?slug=SLUG`.
- The canonical in `blog/post.html` is set dynamically by its inline script from the post's front matter — do not hardcode it.

## Shared CSS and JS

- All styles go in `assets/duct.css`. Never add a `<link>` to a separate page CSS file.
- Page-specific overrides (e.g. accent colour) go in an inline `<style>` block at the bottom of `<head>`. Keep it minimal.
- `assets/config.js` must load **before** `assets/duct.js` — config.js sets `DUCT_CONFIG` that duct.js reads.
- `assets/duct.js` always loads with `defer` at the bottom of `<body>`.
- Asset path: root-level pages use `assets/`, blog pages use `../assets/`.

## Sitemap

- Every new page or blog post requires a `<url>` entry in `sitemap.xml`.
- Use production URLs. No `.html` extensions for landing pages.
- Blog post entries: `https://getduct.ai/blog/post.html?slug=SLUG`
- Landing pages: `<priority>0.9</priority>`, `<changefreq>weekly</changefreq>`
- Blog posts: `<priority>0.7</priority>`, `<changefreq>monthly</changefreq>`

## Google Forms integration

- Form submit buttons must have `data-form-url` and `data-entry-id` attributes.
- Always use `onclick="submitForm('INPUT_ID', this)"` — never handle submission inline.
- Do not add a `<form>` element. The pattern uses a plain `<input>` + `<button>`.
- Copy `data-form-url` and `data-entry-id` from `for-product-intelligence.html` unless the new page needs a distinct form.

## Google Tag Manager

- The GTM noscript `<iframe>` goes immediately after `<body>` — before any other content.
- Never hardcode the GTM ID (`GTM-PKL589SW`) in JavaScript. Always read from `DUCT_CONFIG.gtm`.
- Exception: the noscript iframe in existing files has the ID hardcoded — this is acceptable because noscript cannot run JS. Do not "fix" this.

## New landing page variant pattern

- File name: `for-<audience-slug>.html` (lowercase, hyphens only).
- Copy `for-product-intelligence.html` as the base — it has the fullest section structure.
- Update in order: `<title>`, canonical, `og:url`, `og:title`, `og:description`, nav subtitle, hero headline, hero subtext, form IDs (if new form), audience cards, `<style>` overrides.
- Add the new URL to `sitemap.xml` before committing.

## Blog posts

- Post files: `blog/posts/<slug>.md`
- Slug rules: lowercase, hyphens only, no special characters, descriptive of the title.
- Required front matter keys: `title`, `date`, `author`, `category`, `excerpt`, `readTime`.
- `date` format: `Mon DD YYYY` (e.g. `Mar 15 2026`).
- `readTime` is a bare integer (minutes), no quotes.
- After adding a post, also update:
  1. `blog/index.html` — new `<a class="blog-card reveal">` entry (follow existing markup exactly, newest card first)
  2. `sitemap.xml` — new `<url>` entry

## SEO quality bar

- `<meta name="description">` must be 140–160 characters.
- `og:description` and `twitter:description` can be 120–140 characters.
- `og:image` and `twitter:image` point to `https://getduct.ai/assets/og-image.png` unless the page has a specific image.
- Include `<script type="application/ld+json">` with Schema.org type: landing pages → `WebPage`, blog index → `CollectionPage`, blog posts → `Article` (set dynamically by `blog/post.html`).
