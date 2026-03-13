# Duct

[![Site](https://img.shields.io/badge/site-getduct.ai-orange?style=flat-square&logo=google-chrome&logoColor=white)](https://getduct.ai)

**The intelligence layer for product and growth teams.**

Duct connects your entire tool stack — Mixpanel, Intercom, Linear, Salesforce, GA4, Ahrefs, Google Ads — and automatically synthesises cross-tool insights into a weekly decision brief and real-time alerts. No dashboards to check. No SQL to write. No tab-switching.

Most teams have the data. What they lack is the synthesis. Every tool speaks its own language. Duct is the layer that reads across all of them and tells you what they mean together — delivered to your inbox every Monday morning.

> **One-liner:** Duct connects your product and marketing stack and automatically generates the cross-tool insights your team needs to make faster, better decisions.

---

## Pages

| URL | File | Audience |
|-----|------|----------|
| `/` | `index.html` | Redirects to `/for-product-intelligence` |
| `/for-product-intelligence` | `for-product-intelligence.html` | PMs and product teams |
| `/for-organic-growth` | `for-organic-growth.html` | Growth and content teams |

## Assets

| File | Purpose |
|------|---------|
| `assets/duct.css` | Shared brand styles |
| `assets/duct.js` | Scroll reveal, nav shadow, form submit, GTM init |
| `assets/config.js` | Analytics config — GTM container ID lives here |

## Analytics

GTM container `GTM-PKL589SW` is loaded via `assets/duct.js`. All tags (GA4, Google Ads, X pixel) are configured inside the GTM dashboard — no code changes needed to add or modify tracking.

To update the GTM ID, edit the single line in `assets/config.js`.

## Add a new page

1. Copy `for-product-intelligence.html` → `for-new-audience.html`
2. Update `<title>`, `<link rel="canonical">`, and the nav subtitle
3. Update hero copy and audience cards for the new segment
4. GTM and config are inherited automatically via `duct.js`
