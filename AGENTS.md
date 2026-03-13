# Duct — Agent instructions

Static multi-variant landing site for [getduct.ai](https://getduct.ai). Follow these conventions when editing this project.

## Stack

- **Static site only:** Pure HTML, CSS, and JavaScript. No build tools, no bundler, no framework.
- Do not suggest adding npm, Vite, Webpack, or similar unless explicitly asked.

## Structure

- **URL → file mapping:** Each path corresponds to one HTML file (e.g. `/for-product-managers` → `for-product-managers.html`). Root `/` is `index.html` and redirects to `/for-product-managers`.
- **Shared assets:** Use `assets/duct.css` for brand styles and `assets/duct.js` for scroll reveal, nav shadow, and form submit logic. Do not duplicate these in page-specific files.

## Adding a new variant

1. Copy an existing `for-*.html` (e.g. `for-product-managers.html`) → `for-new-audience.html`.
2. Update `<title>`, `<link rel="canonical">` (use production URL `https://getduct.ai/...`), and hero copy.
3. If using a separate form, update the Google Forms `data-form-url` and `data-entry-id` on both submit buttons.
4. Add the new URL to `sitemap.xml`.

## Deploy

Push to `main`. Netlify, Vercel, or Cloudflare Pages auto-deploy and serve `.html` files at clean URLs (e.g. `for-product-managers.html` → `/for-product-managers`).

## Local dev

- `python3 -m http.server 8080` then open e.g. `http://localhost:8080/for-product-managers.html`.
- Or use the Live Server extension (see `.vscode/settings.json`, port 5500).
