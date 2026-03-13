# Duct Landing Pages

Static multi-variant landing site for [getduct.ai](https://getduct.ai). No build tools — pure HTML/CSS/JS.

## URL → File mapping

| URL | File |
|-----|------|
| `/` | `index.html` (redirects to `/for-product-managers`) |
| `/for-product-managers` | `for-product-managers.html` |
| `/for-organic-growth` | `for-organic-growth.html` |

## Shared assets

- `assets/duct.css` — brand styles shared across all variants
- `assets/duct.js` — scroll reveal, nav shadow, form submit logic

## Local dev

```
python3 -m http.server 8080
```

Then open `http://localhost:8080/for-product-managers.html`.

## Deploy

Push to `main`. Netlify/Vercel/Cloudflare Pages auto-deploys and serves `.html` files at clean URLs (e.g. `for-product-managers.html` → `/for-product-managers`).

## Add a new variant

1. Copy `for-product-managers.html` → `for-new-audience.html`
2. Update `<title>`, `<link rel="canonical">`, and hero copy
3. Update the Google Forms `data-form-url` / `data-entry-id` on both submit buttons if using a separate form
4. Add the new URL to `sitemap.xml`
