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

Dev ports are **pinned** (not framework defaults) so they stay clear of other local stacks:

| Surface | Port |
| --- | --- |
| Next.js (`npm run dev`) | **3003** |
| FastAPI (`uvicorn` in `.vscode` / README-style commands) | **8002** |
| ADK Web | **8003** |
| Static site (`dev_server.py --port …`) | **8090** |

Open the app: `http://localhost:3003/insights`

If you set `NEXT_PUBLIC_APP_URL` for local builds, use `http://localhost:3003` so `metadataBase` matches the dev origin.

For OAuth and CORS, set **`API_PUBLIC_URL`** / **`FRONTEND_ORIGIN`** in `backend/.env` or `backend/.env.local` to `http://localhost:8002` and `http://localhost:3003` respectively when developing against this stack (or override only in your local env). `NEXT_PUBLIC_API_BASE` should match the API origin (`http://localhost:8002` when unset in dev is handled in `src/lib/api.js`).

## Production (Cloudflare Workers)

OpenNext + Wrangler live in this directory (`wrangler.jsonc`, `open-next.config.ts`). Full architecture, env vars, and production deploy (Cloudflare **Workers Builds** from Git) are documented in the deployment runbook (duct-cloud, private).

Optional: `NEXT_PUBLIC_GTM_ID` for Google Tag Manager (GA4 etc. live in the GTM container). See [`src/lib/analytics-client.js`](src/lib/analytics-client.js).

- Local prod-like: `npm run preview:cf`
- Deploy: `npm run deploy:cf` (after `wrangler login`)

## Data source

**Product path (generate flow):** The interactive wizard calls `POST /api/generate` and persists the returned JSON in the **browser** via [`src/lib/localInsights.js`](src/lib/localInsights.js) (`localStorage`). Do not rely on the API host filesystem for user reports in production; when you add accounts, move persistence to a real backend store.

**Dev / demo list:** The reports page also merges in **top-level** JSON files from `backend/data/google_ads/*.json` (e.g. `google-ads-report.json`). The `raw/` subdir is not listed.

## Boundary

- Do not move Python synthesis/render logic into this app.
- Keep report generation in `backend/`.
- Use this app as a viewing layer while MVP remains report-first.
