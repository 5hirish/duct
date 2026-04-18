# Duct Site — Agent instructions

Static multi-variant marketing site for [getduct.ai](https://getduct.ai). Follow these conventions when editing `site/`.

## Stack

- Pure HTML, CSS, and JavaScript only.
- No build tools, bundlers, or frameworks.
- Do not suggest npm, Vite, Webpack, Rollup, React, Vue, or Astro unless explicitly asked.

## Structure

- Landing pages live as `for-*.html` in `site/`.
- Blog index and post shell live in `site/blog/`.
- Blog post markdown lives in `site/blog/posts/`.
- Shared assets live in `site/assets/`.
- Sitemap and robots live in `site/`.

## Shared assets

- Use `site/assets/duct.css` for shared brand styles.
- Use `site/assets/duct.js` for shared page behavior.
- Use `site/assets/config.js` for GTM config.
- Do not duplicate shared styles or scripts in page files.

## URL mapping

- `/` -> `site/index.html`
- `/for-product-intelligence` -> `site/for-product-intelligence.html`
- `/for-organic-growth` -> `site/for-organic-growth.html`
- `/for-paid-ads` -> `site/for-paid-ads.html`
- `/blog/` -> `site/blog/index.html` (use trailing slash in links; bare `/blog` may 404 on static hosts)
- `/blog/post?slug=SLUG` -> `site/blog/post.html`

## Adding a new landing page

1. Copy an existing `site/for-*.html` page.
2. Update title, canonical, hero copy, and audience framing.
3. If needed, update the Google Forms attributes on both CTA buttons.
4. Add the URL to `site/sitemap.xml`.

## Local dev

- From the repo root: `python3 -m http.server 8080 --directory site`
- Cursor/VS Code task **Serve site on :8080** runs `python3 dev_server.py --port 8080` inside `site/` for Cloudflare-style routing; only one server can bind **8080**—if you see address-in-use errors, stop the existing Python process before starting another.
- Then open `http://localhost:8080/`
