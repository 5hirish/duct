# Duct

[![Site](https://img.shields.io/badge/site-getduct.ai-orange?style=flat-square&logo=google-chrome&logoColor=white)](https://getduct.ai)

**The intelligence layer for product and growth teams.**

Duct connects your entire tool stack — Mixpanel, Intercom, Linear, Salesforce, GA4, Ahrefs, Google Ads — and automatically synthesises cross-tool insights into a weekly decision brief and real-time alerts. No dashboards to check. No SQL to write. No tab-switching.

Most teams have the data. What they lack is the synthesis. Every tool speaks its own language. Duct is the layer that reads across all of them and tells you what they mean together — delivered to your inbox every Monday morning.

> **One-liner:** Duct connects your product and marketing stack and automatically generates the cross-tool insights your team needs to make faster, better decisions.

---

## Monorepo Layout

| Path | Purpose |
|------|---------|
| `site/` | Static marketing site, landing pages, blog, shared assets |
| `app/` | Next.js report viewer app (current no-auth shell) |
| `backend/` | Python reporting and synthesis MVP |
| `docs/` | Strategy, GTM, MVP, engineering plans, design specs, and LLM guides ([index](docs/README.md)) |

Directory-local agent instructions live inside each code area as `AGENTS.md`
(`CLAUDE.md` beside it is a symlink to the same file):
- [`backend/AGENTS.md`](backend/AGENTS.md), [`app/AGENTS.md`](app/AGENTS.md)
- [`desktop/AGENTS.md`](desktop/AGENTS.md), [`site/AGENTS.md`](site/AGENTS.md)

## Pages

| URL | File | Audience |
|-----|------|----------|
| `/` | `site/index.html` | Redirects to `/for-product-intelligence` |
| `/for-product-intelligence` | `site/for-product-intelligence.html` | PMs and product teams |
| `/for-organic-growth` | `site/for-organic-growth.html` | Growth and content teams |
| `/for-paid-ads` | `site/for-paid-ads.html` | Paid acquisition teams |

## Assets

| File | Purpose |
|------|---------|
| `site/assets/duct.css` | Shared brand styles |
| `site/assets/duct.js` | Scroll reveal, nav shadow, form submit, GTM init |
| `site/assets/config.js` | Analytics config — GTM container ID lives here |

## Backend MVP

| Path | Purpose |
|------|---------|
| `backend/data/<connector_id>/raw/demo_raw_payload.json` | Static demo raw payload (Google Ads) |
| `backend/service/google/brief.py` | Normalize Google Ads JSON into typed brief payloads |
| `backend/service/google/fetch.py` | Google Ads API campaign fetch (used by API routes) |
| `backend/service/google/schema.py` | Google Ads brief payload types (dataclasses) |
| `backend/data/google_ads/` | `google-ads-report.json` (demo brief), `raw/` |

## Analytics

GTM container `GTM-PKL589SW` is loaded via `site/assets/duct.js`. All tags (GA4, Google Ads, X pixel) are configured inside the GTM dashboard — no code changes needed to add or modify tracking.

To update the GTM ID, edit the single line in `site/assets/config.js`.

## Local dev

```bash
python3 -m http.server 8090 --directory site
```

Then open `http://localhost:8090/`.

## Add a new page

1. Copy `site/for-product-intelligence.html` → `site/for-new-audience.html`
2. Update `<title>`, `<link rel="canonical">`, and the nav subtitle
3. Update hero copy and audience cards for the new segment
4. GTM and config are inherited automatically via `site/assets/duct.js`
