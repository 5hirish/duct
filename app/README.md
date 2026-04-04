# Duct App

Minimal Next.js app shell for rendering backend-generated reports.

## Current scope (no auth)

- app layout shell
- report list page (`/reports`)
- report detail viewer (`/reports/[slug]`)
- file-based artifact loading from `../backend/data/google_ads`

## Local run

```bash
cd app
npm install
npm run dev
```

Open: `http://localhost:3000/reports`

## Data source

The app reads report artifacts produced by the backend API:

- Report list reads `backend/data/google_ads/*.json` at the top level only — keep a single demo brief there (`google-ads-report.json`). Raw demo input lives in `raw/`; API output goes to `generated/` (ignored by the list).

With the backend running from `backend/` (see `backend/README.md`), generate a demo report, for example:

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/report/google_ads" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $DUCT_API_KEY" \
  -d '{"use_demo": true, "theme": "paid_ads", "date_to": "2026-04-03"}'
```

## Boundary

- Do not move Python synthesis/render logic into this app.
- Keep report generation in `backend/`.
- Use this app as a viewing layer while MVP remains report-first.
