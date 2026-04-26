# Duct App

Minimal Next.js app shell for rendering backend-generated reports.

## Current scope (no auth)

- app layout shell
- insights list page (`/insights`)
- insight detail viewer (`/insights/[slug]`)
- file-based artifact loading from `../backend/data/google_ads`

## Local run

```bash
cd app
npm install
npm run dev
```

Open: `http://localhost:3000/insights`

## Production (Cloudflare Workers)

OpenNext + Wrangler live in this directory (`wrangler.jsonc`, `open-next.config.ts`). Full architecture, env vars, and production deploy (Cloudflare **Workers Builds** from Git) are documented in [`docs/engineering/deployment-cloudflare-railway.md`](../docs/engineering/deployment-cloudflare-railway.md).

Optional: `NEXT_PUBLIC_GTM_ID` for Google Tag Manager (GA4 etc. live in the GTM container). See [`src/lib/analytics-client.js`](src/lib/analytics-client.js).

- Local prod-like: `npm run preview:cf`
- Deploy: `npm run deploy:cf` (after `wrangler login`)

## Data source

**Product path (generate flow):** The interactive wizard calls `POST /api/generate` and persists the returned JSON in the **browser** via [`src/lib/localReports.js`](src/lib/localReports.js) (`localStorage`). Do not rely on the API host filesystem for user reports in production; when you add accounts, move persistence to a real backend store.

**Dev / demo list:** The reports page also merges in **top-level** JSON files from `backend/data/google_ads/*.json` (e.g. `google-ads-report.json`). The `raw/` subdir is not listed.

## Boundary

- Do not move Python synthesis/render logic into this app.
- Keep report generation in `backend/`.
- Use this app as a viewing layer while MVP remains report-first.
